"""HTTP API (04 §1). Nothing else talks to the graph. Run: `uvicorn api.app:app --port 8000`."""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from brain import integrity, schema
from brain.actions import Actions, Actor, Refused
from brain.config import MAX, settings
from brain.db import Graph, GuardFailed, WriteMismatch
from brain.tools import Ctx, chain_view, evidence, facts, run_tool, span_items

from .agent import Agent, Session
from brain.ids import now_ms

app = FastAPI(title="Company Brain")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

G = Graph()
AGENT = Agent(G)
ANON: dict[str, Session] = {}
STATE = {"last_token_activity": 0, "next_reset_at": None, "seed_dir": os.environ.get("BRAIN_SEED_DIR", "")}
RATE: dict[str, deque] = defaultdict(deque)
RESET_EVERY_MS = int(os.environ.get("BRAIN_RESET_EVERY_MIN", "60")) * 60_000


# auth

class Caller(BaseModel):
    token: bool
    admin: bool
    user_id: str
    ip: str


def caller(request: Request, authorization: str | None = Header(default=None)) -> Caller:
    tok = (authorization or "").removeprefix("Bearer ").strip()
    admin = bool(tok) and tok == settings.admin_token
    has = admin or (bool(tok) and tok == settings.public_write_token)
    if has:
        STATE["last_token_activity"] = now_ms()
    return Caller(token=has, admin=admin, user_id="judge" if has else "anonymous",
                  ip=request.client.host if request.client else "?")


def _rate(key: str, limit: int, window_ms: int) -> None:
    q = RATE[key]
    t = now_ms()
    while q and q[0] < t - window_ms:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "rate limited")
    q.append(t)


def need_token(c: Caller) -> None:
    if not c.token:
        raise HTTPException(401, "writes need the judges' token")
    _rate(f"w:{c.user_id}", 30, 3_600_000)


def need_admin(c: Caller) -> None:
    if not c.admin:
        raise HTTPException(401, "admin token required")


def _session(sid: str, c: Caller) -> Session:
    if sid in ANON:
        return ANON[sid]
    s = AGENT.load_session(sid)
    if not s:
        raise HTTPException(404, "no such session")
    if not c.token or s.user_id != c.user_id:
        raise HTTPException(403, "session does not belong to this client")
    return s


# sessions and turns

class NewSession(BaseModel):
    acting_as: str | None = None


@app.post("/sessions")
def create_session(body: NewSession, c: Caller = Depends(caller)) -> dict:
    acting = body.acting_as or _default_identity()
    if not c.token:
        s = AGENT.create_session("anonymous", acting, anonymous=True)
        ANON[s.id] = s
        return {"session_id": s.id, "anonymous": True, "acting_as": acting}
    s = AGENT.create_session(c.user_id, acting)
    return {"session_id": s.id, "anonymous": False, "acting_as": acting}


def _default_identity() -> str:
    r = G.q("demo_identity")
    if r and r[0]["d"]:
        return r[0]["d"]
    r = G.q("any_person")
    return r[0]["id"] if r else ""


class TurnBody(BaseModel):
    text: str
    as_of: int | None = None
    belief_at: int | None = None
    transcript: list[dict] | None = None


@app.post("/sessions/{sid}/turns")
def post_turn(sid: str, body: TurnBody, c: Caller = Depends(caller)):
    s = _session(sid, c)
    if s.anonymous:
        _rate(f"anon:{c.ip}", 20, 600_000)

    def gen():
        try:
            for ev in AGENT.turn(s, body.text, as_of=body.as_of, belief_at=body.belief_at):
                yield {"event": ev["event"], "data": json.dumps(ev, default=str)}
        except Exception as e:  # noqa: BLE001
            yield {"event": "error", "data": json.dumps({"stage": "turn", "message": str(e)})}

    return EventSourceResponse(gen())


@app.post("/sessions/{sid}/turns/sync")
def post_turn_sync(sid: str, body: TurnBody, c: Caller = Depends(caller)) -> dict:
    """Non-streaming variant (tests, MCP-less clients)."""
    s = _session(sid, c)
    if s.anonymous:
        _rate(f"anon:{c.ip}", 20, 600_000)
    return {"events": [ev for ev in AGENT.turn(s, body.text, as_of=body.as_of, belief_at=body.belief_at)]}


class ActingAs(BaseModel):
    person_id: str


@app.put("/sessions/{sid}/acting-as")
def acting_as(sid: str, body: ActingAs, c: Caller = Depends(caller)) -> dict:
    s = _session(sid, c)
    AGENT.set_acting_as(s, body.person_id)
    return {"session_id": sid, "acting_as": body.person_id}


@app.get("/turns/{turn_id}/trace")
def turn_trace(turn_id: str) -> dict:
    t = AGENT.turn_log.get(turn_id)
    if not t:
        raise HTTPException(404, "unknown turn")
    return t


# reads

def _ctx(as_of: int | None = None) -> Ctx:
    return Ctx(G, now=now_ms(), as_of=as_of)


@app.get("/spans/{span_id}")
def get_span(span_id: str) -> dict:
    r = G.q("span_view", {"id": span_id, "max": MAX})
    if not r:
        raise HTTPException(404)
    return r[0]


@app.get("/sources/{source_id}")
def get_source(source_id: str) -> dict:
    r = G.q("source_view", {"id": source_id})
    if not r:
        raise HTTPException(404)
    src = r[0]["source"]
    spans = sorted([x for x in r[0]["spans"] if x["span"]], key=lambda x: x["ord"] or 0)
    out = {"source": src, "spans": spans, "text": "\n\n".join(x["text"] for x in spans)}
    if src.get("kind") == "draft":
        undone = G.q("draft_status", {"id": source_id})
        out["banner"] = "agent draft: not evidence" + (" · withdrawn" if undone and undone[0]["s"] == "undone" else "")
    return out


@app.get("/paths/{path_id}")
def get_path(path_id: str, pack: str | None = None) -> dict:
    """Path steps with per-edge evidence, resolved from the per-turn pack cache (03 §1.1)."""
    for t in AGENT.turn_log.values():
        for p in t.get("packs", {}).values():
            if pack and p["pack_id"] != pack:
                continue
            for it in p["items"]:
                if (it.get("path") or {}).get("path_id") == path_id:
                    ctx = _ctx(p.get("as_of"))
                    steps = []
                    for st in it["path"]["steps"]:
                        e = st.get("edge")
                        ev = []
                        if e and e.get("aid"):
                            members = [r["id"] for r in G.q("run_members", {"run": e["aid"]})]
                            ev = span_items(evidence(ctx, members or [e["aid"]]))
                        steps.append({**st, "evidence": ev})
                    return {"path_id": path_id, "steps": steps}
    raise HTTPException(404, "unknown path")


@app.get("/overview")
def overview(as_of: int | None = None) -> dict:
    V = as_of or now_ms()
    teams = G.q("overview_teams", {"V": V}, timeout=10000)
    decisions = G.q("overview_decisions", {"V": V})
    pending = G.q("overview_pending")
    disputed = _open_dispute_runs()
    for t in teams:
        for k in ("leads", "members", "owns"):
            t[k] = [x for x in t[k] if x.get("id")]
            for x in t[k]:
                x["disputed"] = x.get("aid") in disputed
    for d in decisions:
        d["affects"] = [x for x in d["affects"] if x.get("id")]
    return {"as_of": V, "teams": teams, "decisions": decisions, "pending": pending}


def _open_dispute_runs() -> dict[str, list[str]]:
    rows = G.q("dispute_chains", {"max": MAX})
    ctx = _ctx()
    out: dict[str, list[str]] = {}
    for r in rows:
        v = chain_view(ctx, r["chain"])
        for run_id, ds in v["disputes"].items():
            opened = [d["assertion_id"] for d in ds if not d["settled"]]
            run = next((x for x in v["state"].runs if x.run_id == run_id), None)
            if opened and run and run.valid_to == MAX:
                out[run_id] = opened
    return out


@app.get("/directory")
def directory(as_of: int | None = None) -> dict:
    """Lists for the Directory page: one call, every entity type, at the As-of date (DESIGN.md §4.3)."""
    V = as_of or now_ms()
    P = {"V": V}
    disputed = _open_dispute_runs()
    systems = G.q("directory_systems", P, timeout=10000)
    projects = G.q("directory_projects", P, timeout=10000)
    people = G.q("directory_people", P, timeout=10000)
    decisions = G.q("directory_decisions", P, timeout=10000)
    tickets = G.q("directory_tickets", P, timeout=10000)
    teams = overview(as_of)["teams"]

    def clean(rows: list[dict], one: tuple[str, ...] = (), many: tuple[str, ...] = ()) -> list[dict]:
        for r in rows:
            for k in one:
                if r.get(k) and not r[k].get("id"):
                    r[k] = None
                if r.get(k):
                    r[k]["disputed"] = r[k].get("aid") in disputed
            for k in many:
                r[k] = [x for x in (r.get(k) or []) if x.get("id")]
                for x in r[k]:
                    x["disputed"] = x.get("aid") in disputed
            r["disputed"] = any((r.get(k) or {}).get("disputed") for k in one) or \
                any(x.get("disputed") for k in many for x in r.get(k, []))
        return rows

    return {
        "as_of": V,
        "teams": teams,
        "systems": clean(systems, one=("owner", "project")),
        "projects": clean(projects, one=("owner",), many=("systems",)),
        "people": clean(people, one=("team",), many=("leads", "decides")),
        "decisions": clean(decisions, many=("affects", "deciders", "replaces", "replaced_by")),
        "tickets": clean(tickets, one=("about", "assignee")),
    }


@app.get("/names")
def names(ids: str = "") -> dict:
    """id (or bare id without its label prefix) -> name and label, for eligibility paths and chips."""
    want = [x for x in ids.split(",") if x]
    if not want:
        return {}
    rows = G.q("names", {"ids": want})
    out: dict[str, dict] = {}
    for r in rows:
        lab = next((x for x in r["labels"] if x != "Entity"), "Entity")
        out[r["id"]] = {"name": r["name"], "label": lab}
        out[r["id"].split(":", 1)[-1]] = {"id": r["id"], "name": r["name"], "label": lab}
    return out


@app.get("/entities/{eid}")
def entity_panel(eid: str, as_of: int | None = None) -> dict:
    ctx = _ctx(as_of)
    label = eid.split(":")[0]
    out: dict[str, Any] = {"id": eid}
    r = G.q("entity", {"id": eid})
    if not r:
        raise HTTPException(404)
    out.update(r[0])
    if label in ("system", "project"):
        out["owner"] = run_tool(ctx, "get_owner", {"entity_id": eid})
        out["depended_on_by"] = run_tool(ctx, "find_paths", {"from_id": eid})
        out["depends_on"] = G.q("depends_on", {"id": eid, "V": ctx.V})
        out["decisions"] = run_tool(ctx, "trace_decision", {"entity_id": eid})
    if label == "team":
        out["lead"] = [{"id": r["lead"], "name": r["name"], "aid": r["aid"]}
                       for r in G.q("lead_at", {"t": eid, "V": ctx.V})]
    out["history"] = {}
    preds = {"system": ["OWNS", "DEPENDS_ON", "PART_OF"], "project": ["OWNS"], "team": ["LEADS", "OWNS"],
             "person": ["LEADS", "MEMBER_OF"], "ticket": ["ASSIGNED_TO", "HAS_STATE", "ABOUT"],
             "decision": ["HAS_STATUS", "REPLACES", "AFFECTS"]}.get(label, [])
    for p in preds:
        out["history"][p] = run_tool(ctx, "get_history", {"entity_id": eid, "predicate": p})
    out["sources"] = G.q("entity_sources", {"id": eid})
    return out


@app.get("/graph")
def graph(as_of: int | None = None, labels: str = "", source_kinds: str = "") -> dict:
    V = as_of or now_ms()
    labs = [x for x in labels.split(",") if x]
    kinds = [x for x in source_kinds.split(",") if x]
    edges = G.q("graph_edges", {"V": V}, timeout=10000)
    aids = sorted({e["aid"] for e in edges})
    kind_rows = G.q("graph_edge_kinds", {"aids": aids, "max": MAX}, timeout=10000) if aids else []
    kmap = {r["aid"]: r["kinds"] for r in kind_rows}
    for e in edges:
        e["kinds"] = kmap.get(e["aid"], [])
    if kinds:
        edges = [e for e in edges if set(e["kinds"]) & set(kinds)]
    nodes = G.q("graph_nodes", timeout=10000)
    ids_on = {e["source"] for e in edges} | {e["target"] for e in edges}
    if kinds:
        mentioned = {r["id"] for r in G.q("graph_mentioned", {"k": kinds}, timeout=10000)}
        ids_on |= mentioned
    nodes = [n for n in nodes if n["id"] in ids_on or not kinds]
    if labs:
        nodes = [n for n in nodes if set(n["labels"]) & set(labs)]
        keep = {n["id"] for n in nodes}
        edges = [e for e in edges if e["source"] in keep and e["target"] in keep]
    disputed = _open_dispute_runs()
    side = []
    for run_id, ds in disputed.items():
        for d in ds:
            r = G.q("dispute_edge", {"id": d})
            if r:
                side.append({"run": run_id, "assertion_id": d, "source": r[0]["s"], "target": r[0]["o"],
                             "statement": r[0]["st"]})
    stale = Actions(G).stale_detection()
    changes = G.q("graph_ticks", timeout=10000)
    return {"as_of": V, "nodes": nodes, "edges": edges, "disputed": side,
            "stale": [{"source": s["s"], "target": s["o"], "doc": s["title"], "why": s["why"], "span": s["span"],
                       "statement": s["statement"]} for s in stale],
            "ticks": [r["t"] for r in changes]}


@app.get("/graph/neighbourhood")
def neighbourhood(ids: str, as_of: int | None = None, hops: int = 1) -> dict:
    V = as_of or now_ms()
    h = max(1, min(2, hops))
    rows = G.q("neighbourhood", {"ids": ids.split(","), "V": V, "h": h})
    nid = sorted({r["source"] for r in rows} | {r["target"] for r in rows})
    nodes = G.q("nodes_by_id", {"ids": nid})
    return {"nodes": nodes, "edges": rows}


@app.get("/edges/{aid}")
def edge(aid: str, as_of: int | None = None) -> dict:
    ctx = _ctx(as_of)
    members = [r["id"] for r in G.q("run_members", {"run": aid})]
    fs = facts(ctx, members or [aid])
    ev = evidence(ctx, [f["assertion_id"] for f in fs])
    return {"aid": aid, "facts": fs, "spans": span_items(ev)}


@app.get("/entities/{eid}/history")
def history(eid: str, predicate: str) -> dict:
    return run_tool(_ctx(), "get_history", {"entity_id": eid, "predicate": predicate})


@app.get("/people")
def people() -> list[dict]:
    V = now_ms()
    rows = G.q("people", {"V": V}, timeout=10000)
    return rows


# actions, previews, confirm, undo

@app.get("/actions/{aid}")
def action_view(aid: str, session_id: str | None = None, c: Caller = Depends(caller)) -> dict:
    pack = run_tool(_ctx(), "explain_action", {"action_id": aid})
    actor = _acting(session_id, c)
    undo = Actions(G).undo_preview(actor, aid) if actor else {"allowed": False, "undoers": []}
    draft = G.q("action_draft", {"id": aid})
    return {"pack": pack, "undo": undo, "draft_source": draft[0]["id"] if draft else None,
            "request_id": str(uuid.uuid4())}


def _acting(session_id: str | None, c: Caller) -> str:
    if not session_id:
        return ""
    if session_id in ANON:
        return ANON[session_id].acting_as
    s = AGENT.load_session(session_id)
    return s.acting_as if s else ""


@app.get("/assertions/{aid}/confirmers")
def confirm_preview_a(aid: str, session_id: str, c: Caller = Depends(caller)) -> dict:
    return {**Actions(G).confirm_preview(_acting(session_id, c), assertion_id=aid), "request_id": str(uuid.uuid4())}


@app.get("/actions/{aid}/confirmers")
def confirm_preview_ac(aid: str, session_id: str, c: Caller = Depends(caller)) -> dict:
    return {**Actions(G).confirm_preview(_acting(session_id, c), action_id=aid), "request_id": str(uuid.uuid4())}


class Click(BaseModel):
    session_id: str
    request_id: str


def _actor(body: Click, c: Caller) -> Actor:
    s = _session(body.session_id, c)
    if s.anonymous:
        raise HTTPException(401, "writes need the judges' token")
    return Actor(s.acting_as, "session_user", c.user_id, s.id, body.request_id)


def _write(fn) -> dict:
    try:
        res = fn()
    except Refused as r:
        return {"refusal": r.as_dict()}
    except (GuardFailed, WriteMismatch) as e:
        raise HTTPException(409, f"conflict: {e}")
    if res.get("action_id"):
        res["pack"] = run_tool(_ctx(), "explain_action", {"action_id": res["action_id"]})
    return res


@app.post("/assertions/{aid}/confirm")
def confirm_a(aid: str, body: Click, c: Caller = Depends(caller)) -> dict:
    need_token(c)
    actor = _actor(body, c)
    return _write(lambda: Actions(G).confirm_fact(actor, assertion_id=aid))


@app.post("/actions/{aid}/confirm")
def confirm_ac(aid: str, body: Click, c: Caller = Depends(caller)) -> dict:
    need_token(c)
    actor = _actor(body, c)
    return _write(lambda: Actions(G).confirm_fact(actor, action_id=aid))


@app.post("/actions/{aid}/undo")
def undo(aid: str, body: Click, c: Caller = Depends(caller)) -> dict:
    need_token(c)
    actor = _actor(body, c)
    return _write(lambda: Actions(G).undo_action(actor, aid))


@app.get("/people/{pid}/pending")
def pending(pid: str) -> dict:
    acts = Actions(G)
    props = G.q("pending_proposals")
    awaiting, mine = [], []
    for p in props:
        pv = acts.confirm_preview(pid, action_id=p["action_id"])
        if pv["admissible"] and pv["actor_eligible"]:
            awaiting.append({**p, "fallback": pv["fallback"], "type": "proposal"})
        if p["actor"] == pid:
            mine.append(p)
    for run_id, ds in _open_dispute_runs().items():
        for d in ds:
            pv = acts.confirm_preview(pid, assertion_id=d)
            if pv["admissible"] and pv["actor_eligible"]:
                st = G.q("statement", {"id": d})
                awaiting.append({"assertion_id": d, "summary": st[0]["s"] if st else d, "fallback": pv["fallback"],
                                 "type": "dispute"})
    log = G.q("action_log", {"p": pid})
    for a in log:
        a["undo"] = acts.undo_preview(pid, a["id"])
    return {"awaiting": awaiting, "mine": mine, "log": log}


# admin, health

class IngestBody(BaseModel):
    render_dir: str


@app.post("/admin/ingest")
def admin_ingest(body: IngestBody, c: Caller = Depends(caller)) -> dict:
    need_admin(c)
    from ingest.pipeline import Ingestor
    rep = Ingestor(G).ingest_render(Path(body.render_dir))
    AGENT._index = None
    return {"counts": rep.counts(), "sources": rep.sources, "skipped": rep.skipped}


@app.post("/admin/rebuild-projections")
def admin_rebuild(c: Caller = Depends(caller)) -> dict:
    need_admin(c)
    return {"chains": integrity.rebuild_projections(G)}


@app.post("/admin/reset")
def admin_reset(c: Caller = Depends(caller)) -> dict:
    need_admin(c)
    return reset_to_seed()


def reset_to_seed() -> dict:
    from brain.cli import reset_seed
    out = reset_seed(G, STATE["seed_dir"] or None)
    AGENT._index = None
    ANON.clear()
    STATE["next_reset_at"] = now_ms() + RESET_EVERY_MS
    return out


@app.get("/admin/integrity")
def admin_integrity(deep: bool = False, c: Caller = Depends(caller)) -> dict:
    need_admin(c)
    return integrity.check(G, deep=deep)


@app.get("/health")
def health() -> dict:
    h = schema.health(G, settings.pin or None)
    h["next_reset_at"] = STATE["next_reset_at"]
    h["past_belief_engine"] = settings.past_belief_engine
    return h


def _scheduler() -> None:
    """Scheduled reset to seed, deferred while a token session was active in the last 30 minutes (A63)."""
    started = now_ms()
    STATE["next_reset_at"] = started + RESET_EVERY_MS
    while True:
        time.sleep(60)
        t = now_ms()
        if STATE["next_reset_at"] and t >= STATE["next_reset_at"]:
            idle = t - STATE["last_token_activity"] > 30 * 60_000
            forced = t - STATE["next_reset_at"] > 6 * 3_600_000
            if idle or forced:
                try:
                    reset_to_seed()
                except Exception:  # noqa: BLE001
                    STATE["next_reset_at"] = t + 10 * 60_000
            else:
                STATE["next_reset_at"] = t + 10 * 60_000


if os.environ.get("BRAIN_SCHEDULED_RESET") == "on":
    threading.Thread(target=_scheduler, daemon=True).start()
