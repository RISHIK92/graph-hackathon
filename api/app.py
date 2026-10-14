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
    r = G.ro("MATCH (s:Source {kind:'world_meta'}) RETURN s.demo_identity AS d LIMIT 1", template="demo_identity")
    if r and r[0]["d"]:
        return r[0]["d"]
    r = G.ro("MATCH (p:Person) RETURN p.id AS id ORDER BY p.id LIMIT 1", template="any_person")
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
    r = G.ro("MATCH (s:Span {id:$id})<-[h:HAS_SPAN]-(src:Source) RETURN s.text AS text, s.kind AS kind, "
             "s.ts AS ts, collect({source:src.id, title:src.title, uri:src.uri, cs:h.char_start, ce:h.char_end, "
             "latest:src.is_latest, live:h.removed_at = $max}) AS revisions", {"id": span_id, "max": MAX},
             template="span_view")
    if not r:
        raise HTTPException(404)
    return r[0]


@app.get("/sources/{source_id}")
def get_source(source_id: str) -> dict:
    r = G.ro("MATCH (s:Source {id:$id}) OPTIONAL MATCH (s)-[h:HAS_SPAN]->(sp:Span) "
             "RETURN s AS source, collect({span:sp.id, text:sp.text, cs:h.char_start, ce:h.char_end, ord:h.ordinal}) AS spans",
             {"id": source_id}, template="source_view")
    if not r:
        raise HTTPException(404)
    src = r[0]["source"]
    spans = sorted([x for x in r[0]["spans"] if x["span"]], key=lambda x: x["ord"] or 0)
    out = {"source": src, "spans": spans, "text": "\n\n".join(x["text"] for x in spans)}
    if src.get("kind") == "draft":
        undone = G.ro("MATCH (ac:Action)-[:PRODUCED]->(:Source {id:$id}) RETURN ac.status AS s", {"id": source_id},
                      template="draft_status")
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
                            members = [r["id"] for r in G.ro("MATCH (a:Assertion {run_id:$r}) RETURN a.id AS id",
                                                             {"r": e["aid"]}, template="run_members")]
                            ev = span_items(evidence(ctx, members or [e["aid"]]))
                        steps.append({**st, "evidence": ev})
                    return {"path_id": path_id, "steps": steps}
    raise HTTPException(404, "unknown path")


@app.get("/overview")
def overview(as_of: int | None = None) -> dict:
    V = as_of or now_ms()
    teams = G.ro(
        "MATCH (t:Team) "
        "OPTIONAL MATCH (p:Person)-[l:LEADS]->(t) WHERE l.valid_from <= $V AND l.valid_to > $V "
        "WITH t, collect({id:p.id, name:p.name, aid:l.aid}) AS leads "
        "OPTIONAL MATCH (m:Person)-[mm:MEMBER_OF]->(t) WHERE mm.primary = true AND mm.valid_from <= $V AND mm.valid_to > $V "
        "WITH t, leads, collect({id:m.id, name:m.name, aid:mm.aid}) AS members "
        "OPTIONAL MATCH (t)-[o:OWNS]->(x:Entity) WHERE o.valid_from <= $V AND o.valid_to > $V "
        "RETURN t.id AS id, t.name AS name, leads, members, collect({id:x.id, name:x.name, aid:o.aid}) AS owns "
        "ORDER BY name", {"V": V}, template="overview_teams", timeout=10000)
    decisions = G.ro(
        "MATCH (d:Decision) WHERE d.status = 'accepted' "
        "OPTIONAL MATCH (d)-[a:AFFECTS]->(x:Entity) WHERE a.valid_from <= $V AND a.valid_to > $V "
        "RETURN d.id AS id, d.name AS name, d.title AS title, d.status_aid AS aid, "
        "collect({id:x.id, name:x.name, aid:a.aid}) AS affects ORDER BY name", {"V": V}, template="overview_decisions")
    pending = G.ro("MATCH (ac:Action) WHERE ac.kind IN ['draft_adr_supersession','route_to_owner'] AND ac.status = 'done' "
                   "MATCH (ac)-[:PRODUCED]->(p:Assertion) WHERE p.status = 'proposed' "
                   "AND NOT (p)<-[:CONFIRMS]-(:Assertion {status:'current'}) "
                   "RETURN DISTINCT ac.id AS action_id, ac.kind AS kind, ac.summary AS summary", template="overview_pending")
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
    rows = G.ro("MATCH (d:Assertion)-[x:DISPUTES]->(m:Assertion) WHERE x.removed_at = $max AND d.status = 'disputed' "
                "RETURN DISTINCT m.chain_id AS chain", {"max": MAX}, template="dispute_chains")
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
    systems = G.ro(
        "MATCH (s:System) "
        "OPTIONAL MATCH (t:Team)-[o:OWNS]->(s) WHERE o.valid_from <= $V AND o.valid_to > $V "
        "WITH s, collect({id:t.id, name:t.name, aid:o.aid})[0] AS owner "
        "OPTIONAL MATCH (s)-[d:DEPENDS_ON]->(:Entity) WHERE d.valid_from <= $V AND d.valid_to > $V "
        "WITH s, owner, count(d) AS depends_on "
        "OPTIONAL MATCH (:Entity)-[u:DEPENDS_ON]->(s) WHERE u.valid_from <= $V AND u.valid_to > $V "
        "WITH s, owner, depends_on, count(u) AS depended_on_by "
        "OPTIONAL MATCH (s)-[pp:PART_OF]->(pr:Project) WHERE pp.valid_from <= $V AND pp.valid_to > $V "
        "WITH s, owner, depends_on, depended_on_by, collect({id:pr.id, name:pr.name})[0] AS project "
        "OPTIONAL MATCH (dc:Decision)-[af:AFFECTS]->(s) WHERE af.valid_from <= $V AND af.valid_to > $V "
        "RETURN s.id AS id, s.name AS name, s.description AS description, owner, project, "
        "depends_on, depended_on_by, count(dc) AS decisions ORDER BY name", P, template="directory_systems", timeout=10000)
    projects = G.ro(
        "MATCH (p:Project) "
        "OPTIONAL MATCH (t:Team)-[o:OWNS]->(p) WHERE o.valid_from <= $V AND o.valid_to > $V "
        "WITH p, collect({id:t.id, name:t.name, aid:o.aid})[0] AS owner "
        "OPTIONAL MATCH (s:System)-[pp:PART_OF]->(p) WHERE pp.valid_from <= $V AND pp.valid_to > $V "
        "WITH p, owner, collect({id:s.id, name:s.name}) AS systems "
        "OPTIONAL MATCH (w:Person)-[wo:WORKS_ON]->(p) WHERE wo.valid_from <= $V AND wo.valid_to > $V "
        "RETURN p.id AS id, p.name AS name, p.description AS description, owner, systems, count(w) AS people "
        "ORDER BY name", P, template="directory_projects", timeout=10000)
    people = G.ro(
        "MATCH (p:Person) "
        "OPTIONAL MATCH (p)-[m:MEMBER_OF]->(t:Team) WHERE m.primary = true AND m.valid_from <= $V AND m.valid_to > $V "
        "WITH p, collect({id:t.id, name:t.name})[0] AS team "
        "OPTIONAL MATCH (p)-[l:LEADS]->(lt:Team) WHERE l.valid_from <= $V AND l.valid_to > $V "
        "WITH p, team, collect({id:lt.id, name:lt.name}) AS leads "
        "OPTIONAL MATCH (d:Decision)-[db:DECIDED_BY]->(p) WHERE db.valid_from <= $V AND db.valid_to > $V "
        "WITH p, team, leads, collect({id:d.id, name:d.name}) AS decides "
        "OPTIONAL MATCH (k:Ticket)-[a:ASSIGNED_TO]->(p) WHERE a.valid_from <= $V AND a.valid_to > $V "
        "RETURN p.id AS id, p.name AS name, p.title AS title, team, leads, decides, count(k) AS tickets "
        "ORDER BY name", P, template="directory_people", timeout=10000)
    decisions = G.ro(
        "MATCH (d:Decision) "
        "OPTIONAL MATCH (d)-[a:AFFECTS]->(x:Entity) WHERE a.valid_from <= $V AND a.valid_to > $V "
        "WITH d, collect({id:x.id, name:x.name, aid:a.aid}) AS affects "
        "OPTIONAL MATCH (d)-[db:DECIDED_BY]->(w:Person) WHERE db.valid_from <= $V AND db.valid_to > $V "
        "WITH d, affects, collect({id:w.id, name:w.name}) AS deciders "
        "OPTIONAL MATCH (d)-[r:REPLACES]->(old:Decision) "
        "WITH d, affects, deciders, collect({id:old.id, name:old.name}) AS replaces "
        "OPTIONAL MATCH (new:Decision)-[r2:REPLACES]->(d) "
        "RETURN d.id AS id, d.name AS name, d.title AS title, d.description AS description, d.status AS status, "
        "d.decided_at AS decided_at, affects, deciders, replaces, collect({id:new.id, name:new.name}) AS replaced_by "
        "ORDER BY name", P, template="directory_decisions", timeout=10000)
    tickets = G.ro(
        "MATCH (k:Ticket) "
        "OPTIONAL MATCH (k)-[ab:ABOUT]->(x:Entity) WHERE ab.valid_from <= $V AND ab.valid_to > $V "
        "WITH k, collect({id:x.id, name:x.name})[0] AS about "
        "OPTIONAL MATCH (k)-[a:ASSIGNED_TO]->(p:Person) WHERE a.valid_from <= $V AND a.valid_to > $V "
        "WITH k, about, collect({id:p.id, name:p.name, aid:a.aid})[0] AS assignee "
        "OPTIONAL MATCH (st:Assertion {subject_id:k.id, predicate:'HAS_STATE'}) "
        "WHERE st.status = 'current' AND st.valid_from <= $V AND st.valid_to > $V "
        "RETURN k.id AS id, k.name AS name, k.description AS description, about, assignee, "
        "collect(st.object_value)[0] AS state ORDER BY name", P, template="directory_tickets", timeout=10000)
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
    rows = G.ro("MATCH (e:Entity) WHERE e.id IN $ids OR any(i IN $ids WHERE e.id ENDS WITH (':' + i)) "
                "RETURN e.id AS id, e.name AS name, labels(e) AS labels", {"ids": want}, template="names")
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
    r = G.ro("MATCH (e:Entity {id:$id}) RETURN e.name AS name, e.description AS d, labels(e) AS labels", {"id": eid},
             template="entity")
    if not r:
        raise HTTPException(404)
    out.update(r[0])
    if label in ("system", "project"):
        out["owner"] = run_tool(ctx, "get_owner", {"entity_id": eid})
        out["depended_on_by"] = run_tool(ctx, "find_paths", {"from_id": eid})
        out["depends_on"] = G.ro("MATCH (x:Entity {id:$id})-[d:DEPENDS_ON]->(y) WHERE d.valid_from <= $V AND d.valid_to > $V "
                 "RETURN y.id AS id, y.name AS name, d.aid AS aid", {"id": eid, "V": ctx.V}, template="depends_on")
        out["decisions"] = run_tool(ctx, "trace_decision", {"entity_id": eid})
    if label == "team":
        out["lead"] = G.ro("MATCH (p:Person)-[l:LEADS]->(:Team {id:$id}) WHERE l.valid_from <= $V AND l.valid_to > $V "
                           "RETURN p.id AS id, p.name AS name, l.aid AS aid", {"id": eid, "V": ctx.V}, template="lead_at")
    out["history"] = {}
    preds = {"system": ["OWNS", "DEPENDS_ON", "PART_OF"], "project": ["OWNS"], "team": ["LEADS", "OWNS"],
             "person": ["LEADS", "MEMBER_OF"], "ticket": ["ASSIGNED_TO", "HAS_STATE", "ABOUT"],
             "decision": ["HAS_STATUS", "REPLACES", "AFFECTS"]}.get(label, [])
    for p in preds:
        out["history"][p] = run_tool(ctx, "get_history", {"entity_id": eid, "predicate": p})
    out["sources"] = G.ro("MATCH (:Entity {id:$id})<-[:MENTIONS]-(s:Span)<-[h:HAS_SPAN]-(src:Source) "
                          "WHERE src.kind <> 'draft' AND src.is_latest = true "
                          "RETURN src.kind AS kind, collect(DISTINCT {id:src.id, title:src.title}) AS sources",
                          {"id": eid}, template="entity_sources")
    return out


@app.get("/graph")
def graph(as_of: int | None = None, labels: str = "", source_kinds: str = "") -> dict:
    V = as_of or now_ms()
    labs = [x for x in labels.split(",") if x]
    kinds = [x for x in source_kinds.split(",") if x]
    edges = G.ro("MATCH (a:Entity)-[e]->(b:Entity) WHERE e.aid IS NOT NULL AND e.valid_from <= $V AND e.valid_to > $V "
                 "RETURN a.id AS source, b.id AS target, type(e) AS type, e.aid AS aid, e.valid_from AS vf, "
                 "e.valid_to AS vt, e.authority AS authority", {"V": V}, template="graph_edges", timeout=10000)
    aids = sorted({e["aid"] for e in edges})
    kind_rows = G.ro("UNWIND $aids AS r MATCH (a:Assertion {run_id:r})-[ev:EVIDENCED_BY]->(s:Span) "
                     "WHERE ev.authority >= 1 AND ev.removed_at = $max RETURN r AS aid, collect(DISTINCT s.kind) AS kinds",
                     {"aids": aids, "max": MAX}, template="graph_edge_kinds", timeout=10000) if aids else []
    kmap = {r["aid"]: r["kinds"] for r in kind_rows}
    for e in edges:
        e["kinds"] = kmap.get(e["aid"], [])
    if kinds:
        edges = [e for e in edges if set(e["kinds"]) & set(kinds)]
    nodes = G.ro("MATCH (n:Entity) RETURN n.id AS id, n.name AS name, labels(n) AS labels", template="graph_nodes",
                 timeout=10000)
    ids_on = {e["source"] for e in edges} | {e["target"] for e in edges}
    if kinds:
        mentioned = {r["id"] for r in G.ro("MATCH (s:Span)-[:MENTIONS]->(n:Entity) WHERE s.kind IN $k RETURN DISTINCT n.id AS id",
                                           {"k": kinds}, template="graph_mentioned", timeout=10000)}
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
            r = G.ro("MATCH (a:Assertion {id:$id}) RETURN a.subject_id AS s, a.object_id AS o, a.statement AS st",
                     {"id": d}, template="dispute_edge")
            if r:
                side.append({"run": run_id, "assertion_id": d, "source": r[0]["s"], "target": r[0]["o"],
                             "statement": r[0]["st"]})
    stale = Actions(G).stale_detection()
    changes = G.ro("MATCH ()-[e]->() WHERE e.aid IS NOT NULL AND e.valid_from > 0 RETURN DISTINCT e.valid_from AS t "
                   "ORDER BY t", template="graph_ticks", timeout=10000)
    return {"as_of": V, "nodes": nodes, "edges": edges, "disputed": side,
            "stale": [{"source": s["s"], "target": s["o"], "doc": s["title"], "why": s["why"], "span": s["span"],
                       "statement": s["statement"]} for s in stale],
            "ticks": [r["t"] for r in changes]}


@app.get("/graph/neighbourhood")
def neighbourhood(ids: str, as_of: int | None = None, hops: int = 1) -> dict:
    V = as_of or now_ms()
    h = max(1, min(2, hops))
    typ = "|".join(__import__("brain.registry", fromlist=["PROJECTION_TYPES"]).PROJECTION_TYPES)
    rows = G.ro(f"UNWIND $ids AS i MATCH p = (x:Entity {{id:i}})-[:{typ}*1..{h}]-(y:Entity) "
                "WHERE all(e IN relationships(p) WHERE e.aid IS NOT NULL AND e.valid_from <= $V AND e.valid_to > $V) "
                "UNWIND relationships(p) AS e RETURN DISTINCT startNode(e).id AS source, endNode(e).id AS target, "
                "type(e) AS type, e.aid AS aid LIMIT 300", {"ids": ids.split(","), "V": V}, template="neighbourhood")
    nid = sorted({r["source"] for r in rows} | {r["target"] for r in rows})
    nodes = G.ro("UNWIND $ids AS i MATCH (n:Entity {id:i}) RETURN n.id AS id, n.name AS name, labels(n) AS labels",
                 {"ids": nid}, template="nodes_by_id")
    return {"nodes": nodes, "edges": rows}


@app.get("/edges/{aid}")
def edge(aid: str, as_of: int | None = None) -> dict:
    ctx = _ctx(as_of)
    members = [r["id"] for r in G.ro("MATCH (a:Assertion {run_id:$r}) RETURN a.id AS id", {"r": aid}, template="run_members")]
    fs = facts(ctx, members or [aid])
    ev = evidence(ctx, [f["assertion_id"] for f in fs])
    return {"aid": aid, "facts": fs, "spans": span_items(ev)}


@app.get("/entities/{eid}/history")
def history(eid: str, predicate: str) -> dict:
    return run_tool(_ctx(), "get_history", {"entity_id": eid, "predicate": predicate})


@app.get("/people")
def people() -> list[dict]:
    V = now_ms()
    rows = G.ro("MATCH (p:Person) "
                "OPTIONAL MATCH (p)-[m:MEMBER_OF]->(t:Team) WHERE m.primary = true AND m.valid_from <= $V AND m.valid_to > $V "
                "WITH p, collect(t.name) AS team "
                "OPTIONAL MATCH (p)-[l:LEADS]->(lt:Team) WHERE l.valid_from <= $V AND l.valid_to > $V "
                "WITH p, team, collect(lt.name) AS leads "
                "OPTIONAL MATCH (d:Decision)-[db:DECIDED_BY]->(p) WHERE db.valid_to > $V "
                "RETURN p.id AS id, p.name AS name, p.title AS title, team, leads, collect(d.name) AS decides "
                "ORDER BY name", {"V": V}, template="people", timeout=10000)
    return rows


# actions, previews, confirm, undo

@app.get("/actions/{aid}")
def action_view(aid: str, session_id: str | None = None, c: Caller = Depends(caller)) -> dict:
    pack = run_tool(_ctx(), "explain_action", {"action_id": aid})
    actor = _acting(session_id, c)
    undo = Actions(G).undo_preview(actor, aid) if actor else {"allowed": False, "undoers": []}
    draft = G.ro("MATCH (:Action {id:$id})-[:PRODUCED]->(s:Source {kind:'draft'}) RETURN s.id AS id", {"id": aid},
                 template="action_draft")
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
    props = G.ro("MATCH (ac:Action)-[:PRODUCED]->(p:Assertion) WHERE p.status = 'proposed' AND ac.status = 'done' "
                 "AND NOT (p)<-[:CONFIRMS]-(:Assertion {status:'current'}) "
                 "RETURN DISTINCT ac.id AS action_id, ac.kind AS kind, ac.summary AS summary, ac.actor AS actor",
                 template="pending_proposals")
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
                st = G.ro("MATCH (a:Assertion {id:$id}) RETURN a.statement AS s", {"id": d}, template="statement")
                awaiting.append({"assertion_id": d, "summary": st[0]["s"] if st else d, "fallback": pv["fallback"],
                                 "type": "dispute"})
    log = G.ro("MATCH (ac:Action {actor:$p}) RETURN ac.id AS id, ac.kind AS kind, ac.status AS status, "
               "ac.summary AS summary, ac.recorded_at AS at ORDER BY at DESC LIMIT 50", {"p": pid}, template="action_log")
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
