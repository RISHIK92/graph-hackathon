"""HTTP API (04 §1). Nothing else talks to the graph. Run: `uvicorn api.app:app --port 8000`."""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
import zipfile
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import run_in_threadpool

from brain import integrity, schema
from brain.actions import Actions, Actor, Refused
from brain.config import MAX, settings
from brain.db import Graph, GuardFailed, WriteMismatch
from brain.tools import Ctx, chain_view, evidence, facts, run_tool, span_items

from . import accounts, jobs, workspaces
from .agent import Agent, Session
from brain.ids import now_ms

app = FastAPI(title="Nodus")
if accounts.enabled():   # a session cookie needs credentialed CORS, so only the UI's own origins (item 24)
    app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("NODUS_UI_ORIGINS", "http://localhost:3000").split(","),
                       allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
else:
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(accounts.router)


class _Current:
    """The request's workspace graph or agent, or the shared demo company's when no one is logged in (item 24
    step 2). Every route reads G and AGENT, so one lookup per request moves them all to the workspace."""

    def __init__(self, attr: str, default: Any):
        object.__setattr__(self, "_attr", attr)
        object.__setattr__(self, "_default", default)

    def _target(self) -> Any:
        w = workspaces.current()
        return getattr(w, self._attr) if w else self._default

    def __getattr__(self, k: str) -> Any:
        return getattr(self._target(), k)

    def __setattr__(self, k: str, v: Any) -> None:
        setattr(self._target(), k, v)


_DEFAULT_G = Graph()
_DEFAULT_AGENT = Agent(_DEFAULT_G)
G: Any = _Current("g", _DEFAULT_G)
AGENT: Any = _Current("agent", _DEFAULT_AGENT)


class _WorkspaceMiddleware:
    """Sets the request's workspace from the session cookie, for the whole request, streaming included (a pure
    ASGI middleware, so a server-sent turn runs inside it). Flag off or logged out: the shared graph."""

    def __init__(self, inner: Any):
        self.inner = inner

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http" or not accounts.enabled():
            return await self.inner(scope, receive, send)
        acct = await run_in_threadpool(accounts.current, Request(scope))
        if not acct:
            return await self.inner(scope, receive, send)
        w = await run_in_threadpool(workspaces.get, acct["workspace"])
        tok = workspaces.enter(w)
        try:
            await self.inner(scope, receive, send)
        finally:
            workspaces.leave(tok)


app.add_middleware(_WorkspaceMiddleware)
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
    workspace: str | None = None   # the logged-in account's workspace graph (NODUS_ACCOUNTS=on)


def caller(request: Request, authorization: str | None = Header(default=None)) -> Caller:
    tok = (authorization or "").removeprefix("Bearer ").strip()
    admin = bool(tok) and tok == settings.admin_token
    has = admin or (bool(tok) and tok == settings.public_write_token and not accounts.enabled())
    ip = request.client.host if request.client else "?"
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd and os.environ.get("BRAIN_TRUST_PROXY") == "on":   # behind Caddy (deploy): the client's own address
        ip = fwd.split(",")[0].strip()
    acct = None if has else accounts.current(request)
    if acct:   # the account owner writes in their own workspace; this replaces the public write token (item 24)
        accounts.check_csrf(request, acct)
        return Caller(token=True, admin=False, user_id=f"acct_{acct['id']}", ip=ip, workspace=acct["workspace"])
    if has:
        STATE["last_token_activity"] = now_ms()
    return Caller(token=has, admin=admin, user_id="judge" if has else "anonymous", ip=ip)


def turn_limit(c: Caller) -> None:
    """Every session's turns, per client IP and hour (deploy); anonymous turns also have their own limit."""
    _rate(f"turn:{c.ip}", int(os.environ.get("BRAIN_TURNS_PER_IP_HOUR", "60")), 3_600_000)


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
    turn_limit(c)
    if s.anonymous:
        _rate(f"anon:{c.ip}", 20, 600_000)

    turn = AGENT.turn   # the request's workspace agent, bound now rather than when the stream starts

    def gen():
        try:
            for ev in turn(s, body.text, as_of=body.as_of, belief_at=body.belief_at):
                yield {"event": ev["event"], "data": json.dumps(ev, default=str)}
        except Exception as e:  # noqa: BLE001
            yield {"event": "error", "data": json.dumps({"stage": "turn", "message": str(e)})}

    return EventSourceResponse(gen())


@app.post("/sessions/{sid}/turns/sync")
def post_turn_sync(sid: str, body: TurnBody, c: Caller = Depends(caller)) -> dict:
    """Non-streaming variant (tests, MCP-less clients)."""
    s = _session(sid, c)
    turn_limit(c)
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


@app.get("/gaps")
def gaps(as_of: int | None = None) -> dict:
    """Knowledge gaps at the As-of date (item 20): systems with no owner who has a lead, and teams with no lead,
    as the knowledge_gaps evidence pack, each gap citing the ownership facts it counts. Read-only."""
    return run_tool(_ctx(as_of), "knowledge_gaps", {})


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
    if label == "person":
        # m24: title and team, what they lead and decide, and what their teams own; from the Directory's queries
        me = next((r for r in G.q("directory_people", {"V": ctx.V}, timeout=10000) if r["id"] == eid), None) or {}
        teams = {x["id"] for x in me.get("leads") or [] if x.get("id")} | {(me.get("team") or {}).get("id")}
        owns = [x for t in overview(as_of)["teams"] if t["id"] in teams for x in t["owns"]]
        out["profile"] = {"title": me.get("title"), "team": me.get("team") if (me.get("team") or {}).get("id") else None,
                          "leads": [x for x in me.get("leads") or [] if x.get("id")],
                          "decides": [x for x in me.get("decides") or [] if x.get("id")],
                          "owns_via_team": list({x["id"]: x for x in owns}.values())}
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
    # M10: a decision made after V isn't drawn yet (other entities carry no creation date)
    nodes = [n for n in G.q("graph_nodes", timeout=10000) if not (n.get("decided_at") and n["decided_at"] > V)]
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
            "ticks": [r["t"] for r in changes], "changes": changes}


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


def _awaiting(acts: Actions, pid: str, props: list[dict]) -> list[dict]:
    awaiting = []
    for p in props:
        pv = acts.confirm_preview(pid, action_id=p["action_id"])
        if pv["admissible"] and pv["actor_eligible"]:
            awaiting.append({**p, "fallback": pv["fallback"], "type": "proposal"})
    for run_id, ds in _open_dispute_runs().items():
        members = G.q("run_members", {"run": run_id})
        rec = G.q("statement", {"id": members[0]["id"]}) if members else []
        for d in ds:
            pv = acts.confirm_preview(pid, assertion_id=d)
            if pv["admissible"] and pv["actor_eligible"]:
                st = G.q("statement", {"id": d})
                ch = st[0]["s"] if st else d
                recorded = rec[0]["s"] if rec else ""
                # M18: both sides, and why anyone may settle it when the fallback applies
                awaiting.append({"assertion_id": d, "recorded": recorded, "challenger": ch,
                                 "summary": f"{recorded} (recorded) vs {ch} (challenger)" if recorded else ch,
                                 "fallback": pv["fallback"], "missing_fact": pv.get("missing_fact"), "type": "dispute"})
    return awaiting


@app.get("/people/{pid}/pending")
def pending(pid: str) -> dict:
    acts = Actions(G)
    props = G.q("pending_proposals")
    awaiting = _awaiting(acts, pid, props)
    mine = [p for p in props if p["actor"] == pid]
    log = G.q("action_log", {"p": pid})
    for a in log:
        a["undo"] = acts.undo_preview(pid, a["id"])
    return {"awaiting": awaiting, "mine": mine, "log": log}


@app.get("/people/{pid}/pending/count")
def pending_count(pid: str) -> dict:
    """How many proposals and disputes this person can settle now (the Inbox nav badge)."""
    return {"awaiting": len(_awaiting(Actions(G), pid, G.q("pending_proposals")))}


# admin, health

class IngestBody(BaseModel):
    render_dir: str


UPLOAD_MAX = 20 * 1024 * 1024


@app.post("/admin/upload")
async def admin_upload(filename: str, request: Request, c: Caller = Depends(caller)) -> dict:
    """Ingest one uploaded file (the raw request body): Markdown or plain text as a wiki page, or a Slack
    export (a channel .json or the whole .zip) as chat messages, through the same connectors and pipeline."""
    if not (c.admin or c.workspace):   # an account owner uploads into their own workspace (item 24)
        need_admin(c)
    data = await request.body()
    if len(data) > UPLOAD_MAX:
        raise HTTPException(413, "upload over 20 MB")
    if c.workspace:
        _workspace_room()
    from ingest.pipeline import Ingestor
    try:
        rep = await run_in_threadpool(Ingestor(G).ingest_upload, filename, data)
    except (ValueError, UnicodeDecodeError, KeyError, zipfile.BadZipFile) as e:
        raise HTTPException(400, f"can't read {filename}: {e}")
    AGENT._index = None
    return {"counts": rep.counts(), "sources": rep.sources, "skipped": rep.skipped}


def _workspace_room() -> None:
    cap = int(os.environ.get("NODUS_WS_MAX_SOURCES", "500"))
    n = G.ro("MATCH (s:Source) WHERE s.kind <> 'chat_session' RETURN count(s) AS n", template="workspace")[0]["n"]
    if n >= cap:
        raise HTTPException(413, f"this workspace is at its limit of {cap} sources")


def _need_workspace(c: Caller) -> str:
    if not c.workspace:
        raise HTTPException(401, "log in to use a workspace")
    return c.workspace


@app.get("/workspace")
def workspace_status(c: Caller = Depends(caller)) -> dict:
    """The logged-in account's workspace: whether it is empty, and what it holds."""
    name = _need_workspace(c)
    row = G.ro("OPTIONAL MATCH (s:Source) WHERE s.kind <> 'chat_session' WITH count(s) AS sources "
               "OPTIONAL MATCH (e:Entity) WITH sources, count(e) AS entities "
               "OPTIONAL MATCH (a:Assertion) RETURN sources, entities, count(a) AS facts", template="workspace")[0]
    return {"workspace": name, "empty": row["sources"] == 0, "counts": row}


def demo_template() -> Graph:
    """The demo company as a template graph, built once from the seed with cached extractions; "Load the
    demo company" copies it into a workspace (item 24 step 3)."""
    g = Graph(name=os.environ.get("NODUS_DEMO_TEMPLATE", "nodus_demo_template"))
    try:
        ready = g.ro("MATCH (s:Source) RETURN count(s) AS n", template="workspace")[0]["n"] > 0
    except Exception:  # noqa: BLE001 - not built yet
        ready = False
    if not ready:
        from brain.cli import reset_seed
        reset_seed(g, STATE["seed_dir"] or None)
    return g


def _progress(job: dict, ing: Any) -> None:
    def on(done: int, total: int) -> None:
        rows = ing.report.rows
        job.update(docs=done, total=total, facts=sum(1 for r in rows if r.get("chain")),
                   disputes=sum(1 for r in rows if r.get("outcome") == "disputed"))
    ing.on_doc = on


@app.post("/workspace/ingest")
async def workspace_ingest(filename: str, request: Request, c: Caller = Depends(caller)) -> dict:
    """Ingest one uploaded file into the workspace as a job; poll /workspace/jobs/{id} for its progress."""
    name = _need_workspace(c)
    data = await request.body()
    if len(data) > UPLOAD_MAX:
        raise HTTPException(413, "upload over 20 MB")
    _workspace_room()
    from ingest.pipeline import Ingestor
    g, agent = G._target(), AGENT._target()

    def run(job: dict) -> None:
        ing = Ingestor(g)
        _progress(job, ing)
        try:
            ing.ingest_upload(filename, data)
        except (ValueError, UnicodeDecodeError, KeyError, zipfile.BadZipFile) as e:
            raise ValueError(f"can't read {filename}: {e}") from e
        agent._index = None
    return {"job_id": jobs.start(name, "ingest", run)["id"]}


@app.post("/workspace/demo")
def workspace_demo(c: Caller = Depends(caller)) -> dict:
    """Load the demo company into this workspace (a copy of the template graph), as a job."""
    name = _need_workspace(c)

    def run(job: dict) -> None:
        src = demo_template()
        job.update(total=1)
        workspaces.copy_into(src, name)
        w = workspaces.get(name)
        n = w.g.ro("MATCH (s:Source) WITH count(s) AS docs OPTIONAL MATCH (a:Assertion) WITH docs, count(a) AS facts "
                   "OPTIONAL MATCH (d:Assertion {status:'disputed'}) RETURN docs, facts, count(d) AS disputes",
                   template="workspace")[0]
        job.update(docs=n["docs"], total=n["docs"], facts=n["facts"], disputes=n["disputes"])
    return {"job_id": jobs.start(name, "demo", run)["id"]}


@app.get("/workspace/jobs/{job_id}")
def workspace_job(job_id: str, c: Caller = Depends(caller)) -> dict:
    """An ingest job's state and progress: documents done of total, facts and disputes found."""
    j = jobs.get(job_id, _need_workspace(c))
    if not j:
        raise HTTPException(404, "no such job")
    return j


@app.post("/workspace/reset")
def workspace_reset(c: Caller = Depends(caller)) -> dict:
    """Empty the logged-in account's workspace: its graph is dropped and starts again with the schema only."""
    name = _need_workspace(c)
    workspaces.drop(name)
    workspaces.get(name)
    return {"workspace": name, "empty": True}


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


def empty_demo_workspace() -> str | None:
    """Empty the shared demo account's workspace (user decision: it starts with nothing ingested, nightly)."""
    email, pw = accounts.demo_credentials()
    if not (accounts.enabled() and email and pw):
        return None
    name = accounts.store().ensure_demo(email, pw)["workspace"]
    workspaces.drop(name)
    workspaces.get(name)
    return name


def _demo_nightly() -> None:
    day = time.strftime("%Y-%m-%d", time.gmtime())
    while True:
        time.sleep(600)
        today = time.strftime("%Y-%m-%d", time.gmtime())
        if today != day:
            day = today
            try:
                empty_demo_workspace()
            except Exception:  # noqa: BLE001 - try again the next night
                pass


if os.environ.get("BRAIN_SCHEDULED_RESET") == "on":
    threading.Thread(target=_scheduler, daemon=True).start()
if accounts.enabled() and os.environ.get("NODUS_DEMO_NIGHTLY_RESET", "on") == "on":
    threading.Thread(target=_demo_nightly, daemon=True).start()
