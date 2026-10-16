"""Graph performance benchmark (item 20 step 4): p50/p95 per read template, per algorithm tool and for the
snapshot rebuild, at seed scale and 10x, on each FalkorDB version.

World. Scale 1 is `reset_seed` of seed 1 into a throwaway graph `perf_x<scale>`. Scale N adds N-1 clones of
that graph, loaded through the product's own write layers, never by copying nodes:
  - entities via `store.upsert_entities` with ids `<id>-k<n>`, names `<name> K<n>` and aliases suffixed the
    same way (embeddings copied);
  - Sources (`<doc_key>-k<n>@<rev>`), Spans (fresh `sp_` ids, same text, ts and embedding), HAS_SPAN (closed
    again with `store.close_has_span` where the original was closed), NEXT, REVISES, MENTIONS, AUTHORED_BY,
    HAS_SOURCE and MOTIVATED_BY via `brain.store`;
  - every Assertion by replaying its EVIDENCED_BY edges as `Candidate`s through `WritePath`, in recorded
    order, one plan per chain per source as ingest does (`execute` checks the guard row and the counters,
    F18). Evidence the original later removed or marked replaced is then closed the same way ingest step 9
    does, the touched chains are recomputed and unsupported assertions retracted (`Ingestor` helpers);
  - per clone, two DEPENDS_ON and two MEMBER_OF facts into the previous clone, from a `perf:links` Source, so
    the world is one connected org rather than N islands.
Each clone's Assertion status counts must equal the original's, or the build fails.

Workload, per version and scale: every eval question offline through `api.agent.Agent` (plain questions,
then token-session and multi-turn ones, then setup-script ones with their scripts run in place), at scale
> 1 also a sample rewritten to name the last clone's entities; the API panel reads; each algorithm tool
repeated on a warm snapshot; the snapshot rebuild timed cold; one Markdown upload through ingest. Reads that
need writes first come last, so the clean-graph reads see the world as built.

Timings are the client-side ms `brain.db.Graph` logs per query (QueryLog), so they include the network round
trip to FalkorDB in local Docker. Tool and rebuild times are wall-clock around the call.

`python -m evals.perf --scale 1 10 --versions 6.0.1 4.22.0 --questions <questions-seed1.jsonl> --out <dir>`
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import time
from collections import defaultdict
from pathlib import Path

os.environ["BRAIN_LLM"] = "off"
os.environ["BRAIN_SCHEDULED_RESET"] = "off"

from brain import integrity, registry, snapshot, store, templates  # noqa: E402
from brain.cli import reset_seed  # noqa: E402
from brain.config import MAX, ROOT  # noqa: E402
from brain.db import Graph, WriteMismatch, with_params  # noqa: E402
from brain.ids import now_ms  # noqa: E402
from brain.tools import Ctx, run_tool  # noqa: E402
from brain.write_path import Candidate, WritePath  # noqa: E402

SEED = ROOT / "world" / "seeds" / "1"
PORTS = {"6.0.1": 6391, "4.22.0": 6392}
MODULE = {"6.0.1": 60001, "4.22.0": 42200}
TARGET = {"template_p95": 50.0, "tool_p95": 200.0, "rebuild_s": 2.0}
ALGO = ("critical_systems", "connection_between", "key_people", "knowledge_gaps")

SAMPLES: list[dict] = []
PHASE = ["build"]


def _record(kind):
    def wrap(fn):
        def inner(self, cypher, params=None, *a, **kw):
            out = fn(self, cypher, params, *a, **kw)
            last = self.log[-1]
            SAMPLES.append({"phase": PHASE[0], "kind": kind, "template": last.template, "graph": self.name,
                            "ms": last.ms, "cypher": cypher, "params": params or {}})
            return out
        return inner
    return wrap


Graph.ro = _record("read")(Graph.ro)
Graph.write = _record("write")(Graph.write)


# World

def _cid(eid: str, k: int) -> str:
    return f"{eid}-k{k}" if eid else eid


def _csrc(sid: str, k: int) -> str:
    key, _, rev = sid.partition("@")
    return f"{key}-k{k}@{rev}" if rev else f"{key}-k{k}"


def _cspan(sp: str, k: int) -> str:
    return "sp_" + hashlib.sha256(f"{sp}|k{k}".encode()).hexdigest()[:16]


def _base(g: Graph) -> dict:
    t = 10000
    b = {
        "entities": [r["e"] for r in g.ro("MATCH (e:Entity) RETURN e", timeout=t)],
        "sources": [r["s"] for r in g.ro("MATCH (s:Source) WHERE s.kind <> 'world_meta' RETURN s", timeout=t)],
        "spans": g.ro("MATCH (src:Source)-[h:HAS_SPAN]->(s:Span) RETURN src.id AS src, h AS h, s AS s", timeout=t),
        "next": g.ro("MATCH (a:Span)-[n:NEXT]->(b:Span) RETURN a.id AS a, b.id AS b, n.doc_key AS k", timeout=t),
        "revises": g.ro("MATCH (n:Source)-[:REVISES]->(o:Source) RETURN n.id AS n, o.id AS o", timeout=t),
        "mentions": g.ro("MATCH (s:Span)-[m:MENTIONS]->(e:Entity) RETURN s.id AS s, e.id AS e, m AS m", timeout=t),
        "authored": g.ro("MATCH (s:Span)-[:AUTHORED_BY]->(p:Person) RETURN s.id AS s, p.id AS p", timeout=t),
        "has_source": g.ro("MATCH (t:Ticket)-[:HAS_SOURCE]->(s:Source) RETURN t.id AS t, s.id AS s", timeout=t),
        "motivated": g.ro("MATCH (d:Decision)-[m:MOTIVATED_BY]->(s:Span) RETURN d.id AS d, s.id AS s, "
                          "m.section AS sec", timeout=t),
        "evidence": g.ro("MATCH (a:Assertion)-[e:EVIDENCED_BY]->(s:Span) WHERE e.action_id = '' "
                         "RETURN a AS a, e AS e, s.id AS span ORDER BY e.recorded_at, a.id, s.id", timeout=t),
        "status": _status(g),
    }
    b["names"] = {e["id"]: e["name"] for e in b["entities"]}
    return b


def _status(g: Graph, k: int | None = None) -> dict:
    where = "WHERE a.subject_id ENDS WITH $suf" if k else ""   # without k: called before any clone exists
    rows = g.ro(f"MATCH (a:Assertion) {where} RETURN a.status AS s, count(*) AS c", {"suf": f"-k{k}"} if k else None,
                timeout=10000)
    return {r["s"]: r["c"] for r in rows}


def _clone(g: Graph, b: dict, k: int) -> None:
    from ingest.pipeline import Ingestor
    ents = []
    for e in b["entities"]:
        props = {x: v for x, v in e.items() if x not in ("_labels", "embedding", "aliases_text")}
        props.update(id=_cid(e["id"], k), name=f"{e['name']} K{k}",
                     aliases=[f"{a} k{k}" for a in e.get("aliases") or []])
        ents.append(props)
    store.upsert_entities(g, ents)
    emb = [{"id": _cid(e["id"], k), "e": e["embedding"]} for e in b["entities"] if e.get("embedding")]
    for i in range(0, len(emb), 100):
        g.write("UNWIND $rows AS x MATCH (n:Entity {id:x.id}) SET n.embedding = vecf32(x.e)", {"rows": emb[i:i + 100]},
                template="entity_embeddings")
    for s in b["sources"]:
        store.create_source(g, {**{x: v for x, v in s.items() if x != "_labels"}, "id": _csrc(s["id"], k),
                                "doc_key": f"{s['doc_key']}-k{k}", "external_id": f"{s.get('external_id') or ''}-k{k}",
                                "title": f"{s.get('title', '')} K{k}"})
    by_src: dict[str, list[dict]] = defaultdict(list)
    for r in b["spans"]:
        by_src[r["src"]].append(r)
    for src, rows in by_src.items():
        spans = []
        for r in rows:
            s, h = r["s"], r["h"]
            spans.append({**{x: s[x] for x in ("text", "keys", "ts", "author_role", "kind", "embed_model") if x in s},
                          "id": _cspan(s["id"], k), "doc_key": f"{s['doc_key']}-k{k}",
                          "author_id": _cid(s["author_id"], k) if s.get("author_id", "").startswith("person:")
                          else s.get("author_id", ""),
                          "char_start": h["char_start"], "char_end": h["char_end"], "ordinal": h["ordinal"],
                          "heading_path": h.get("heading_path", ""), "embedding": s.get("embedding")})
        rm = rows[0]["h"]["removed_at"]
        store.upsert_spans(g, _csrc(src, k), spans, latest=rm != 0)
        if 0 < rm < MAX:
            store.close_has_span(g, _csrc(src, k), now_ms())
    chains: dict[str, dict[str, str]] = defaultdict(dict)
    for r in b["next"]:
        chains[r["k"]][r["a"]] = r["b"]
    for key, nxt in chains.items():
        first = (set(nxt) - set(nxt.values())).pop()
        order = [first]
        while order[-1] in nxt:
            order.append(nxt[order[-1]])
        store.set_next_chain(g, f"{key}-k{k}", [_cspan(x, k) for x in order])
    for r in b["revises"]:
        store.link_revision(g, _csrc(r["n"], k), _csrc(r["o"], k))
    store.add_mentions(g, [{"span_id": _cspan(r["s"], k), "entity_id": _cid(r["e"], k), "start": r["m"]["start"],
                            "end": r["m"]["end"], "method": r["m"]["method"], "hedged": r["m"]["hedged"]}
                           for r in b["mentions"]])
    store.add_authored_by(g, [{"span_id": _cspan(r["s"], k), "person_id": _cid(r["p"], k)} for r in b["authored"]])
    for r in b["has_source"]:
        store.add_has_source(g, _cid(r["t"], k), _csrc(r["s"], k))
    for r in b["motivated"]:
        store.add_motivated_by(g, _cid(r["d"], k), _cspan(r["s"], k), r["sec"], now_ms())
    names = {_cid(i, k): f"{n} K{k}" for i, n in b["names"].items()}
    clone_aid = _replay(g, b["evidence"], k, names)
    closes = []
    for r in b["evidence"]:
        e = r["e"]
        if e["removed_at"] != MAX or e["replaced_by"]:
            closes.append({"aid": clone_aid[r["a"]["id"]], "span": _cspan(r["span"], k),
                           "rm": now_ms() if e["removed_at"] != MAX else MAX,
                           "rb": _csrc(e["replaced_by"], k) if e["replaced_by"] else ""})
    if closes:
        res = g.write("UNWIND $x AS x MATCH (a:Assertion {id:x.aid})-[e:EVIDENCED_BY]->(:Span {id:x.span}) "
                      "SET e.removed_at = x.rm, e.replaced_by = x.rb", {"x": closes}, template="perf_close")
        want = sum((x["rm"] != MAX) + (x["rb"] != "") for x in closes)   # unchanged values are not counted
        if res.counters["properties_set"] != want:
            raise WriteMismatch(f"clone {k}: closed {res.counters['properties_set']} != {want}")
    ing = Ingestor(g)
    ing._load_entities()
    ing._recompute(sorted({registry.chain_id(r["a"]["predicate"], r["a"]["qualifier"], _cid(r["a"]["subject_id"], k),
                                             _cid(r["a"]["object_id"], k))
                           for r in b["evidence"] if r["e"]["removed_at"] != MAX or r["e"]["replaced_by"]}))
    ing._retract_unsupported()


def _replay(g: Graph, evidence: list[dict], k: int, names: dict[str, str]) -> dict[str, str]:
    """Every evidence edge as a Candidate, in recorded order; one plan per chain per Source (ingest step 8)."""
    wp = WritePath(g, now_ms, names)
    out: dict[str, str] = {}
    batches: list[tuple[str, dict[str, list]]] = []
    for r in evidence:
        sid = r["e"]["source_id"]
        if not batches or batches[-1][0] != sid:
            batches.append((sid, defaultdict(list)))
        a = r["a"]
        batches[-1][1][a["chain_id"]].append(r)
    for sid, by_chain in batches:
        for rows in by_chain.values():
            plan = wp.new_plan()
            for r in rows:
                a, e = r["a"], r["e"]
                c = Candidate(a["predicate"], _cid(a["subject_id"], k), _cid(a["object_id"], k), a["object_value"],
                              a["qualifier"], a["negated"], a["valid_from"], a["valid_from_basis"],
                              _cspan(r["span"], k), e["quote_start"], e["quote_end"], _csrc(sid, k), e["form"],
                              a["confidence"], a["extractor"])
                out[a["id"]] = wp.add_candidate(plan, c)["assertion_id"]
            wp.execute(plan)
    return out


def _links(g: Graph, b: dict, k: int) -> None:
    """Two DEPENDS_ON and two MEMBER_OF facts from clone k into clone k-1 (k-1 = 1 is the original)."""
    prev = (lambda x: x) if k == 2 else (lambda x: _cid(x, k - 1))
    ids = sorted(b["names"])
    systems = [i for i in ids if i.startswith("system:")]
    people = [i for i in ids if i.startswith("person:")]
    teams = [i for i in ids if i.startswith("team:")]
    facts = [("DEPENDS_ON", _cid(systems[0], k), prev(systems[1])),
             ("DEPENDS_ON", _cid(systems[2], k), prev(systems[3])),
             ("MEMBER_OF", _cid(people[0], k), prev(teams[0])),
             ("MEMBER_OF", _cid(people[1], k), prev(teams[1]))]
    names = {**{i: n for i, n in b["names"].items()}, **{_cid(i, k): f"{n} K{k}" for i, n in b["names"].items()},
             **{_cid(i, k - 1): f"{n} K{k - 1}" for i, n in b["names"].items()}}
    ts = max(r["s"]["ts"] for r in b["spans"])
    sid = f"catalog:perf:links-k{k}@1"
    store.create_source(g, {"id": sid, "doc_key": f"catalog:perf:links-k{k}", "kind": "catalog", "system": "perf",
                            "external_id": f"links-k{k}", "title": f"Cross-org links K{k}", "uri": "",
                            "created_at": ts, "updated_at": ts, "ingested_at": now_ms(), "is_latest": True,
                            "status": "active", "user_id": ""})
    rel = {"DEPENDS_ON": "depends on", "MEMBER_OF": "is a member of"}
    spans, cands = [], []
    for i, (p, s, o) in enumerate(facts):
        text = f"{names[s]} {rel[p]} {names[o]}."
        sp = _cspan(f"links|{i}", k)
        spans.append({"id": sp, "doc_key": f"catalog:perf:links-k{k}", "text": text, "keys": [], "ts": ts,
                      "author_id": "", "author_role": "human", "kind": "catalog", "embed_model": "",
                      "char_start": 0, "char_end": len(text), "ordinal": i, "heading_path": ""})
        cands.append(Candidate(p, s, o, span_id=sp, quote_end=len(text), source_id=sid, valid_from=ts,
                               extractor="structured:perf"))
    store.upsert_spans(g, sid, spans, latest=True)
    wp = WritePath(g, now_ms, names)
    for c in cands:
        plan = wp.new_plan()
        wp.add_candidate(plan, c)
        wp.execute(plan)


def build_world(g: Graph, scale: int) -> dict:
    PHASE[0] = "build"
    report = ROOT / "evals" / "results" / "extraction-report.jsonl"
    keep = report.read_bytes() if report.exists() else None
    t0 = time.perf_counter()
    try:
        reset_seed(g, str(SEED))
    finally:
        if keep is not None:
            report.write_bytes(keep)
    seed_s = time.perf_counter() - t0
    if scale > 1:
        b = _base(g)
        for k in range(2, scale + 1):
            _clone(g, b, k)
            got = _status(g, k)
            if got != b["status"]:
                raise RuntimeError(f"clone {k}: assertion statuses {got} != original {b['status']}")
            _links(g, b, k)
    counts = {
        "nodes": g.ro("MATCH (n) RETURN count(n) AS c", timeout=10000)[0]["c"],
        "edges": g.ro("MATCH ()-[e]->() RETURN count(e) AS c", timeout=10000)[0]["c"],
        "assertions": g.ro("MATCH (a:Assertion) RETURN count(a) AS c", timeout=10000)[0]["c"],
        "spans": g.ro("MATCH (s:Span) RETURN count(s) AS c", timeout=10000)[0]["c"],
        "entities": g.ro("MATCH (e:Entity) RETURN count(e) AS c", timeout=10000)[0]["c"],
    }
    return {"seed_s": round(seed_s, 1), "total_s": round(time.perf_counter() - t0, 1), **counts}


# Workload

def _turns(agent, s, texts: list[str], as_of, belief_at) -> None:
    for text in texts:
        for _ in agent.turn(s, text, as_of=as_of, belief_at=belief_at):
            pass


def _rename(q: str, names: dict[str, str], k: int) -> str:
    alt = "|".join(re.escape(n) for n in sorted(set(names.values()), key=len, reverse=True))
    return re.sub(rf"\b({alt})\b", lambda m: f"{m.group(1)} K{k}", q)


def workload(g: Graph, scale: int, questions: list[dict], reps: int) -> dict:
    import api.app as app
    from api.agent import Agent, Session
    from evals.answer import resolve, run_setup
    from evals.gold import World
    from ingest.pipeline import Ingestor
    app.G = g
    agent = Agent(g)
    names = {e["id"]: e["name"] for e in g.ro("MATCH (e:Entity) RETURN e.id AS id, e.name AS name", timeout=10000)
             if not re.search(r"-k\d+$", e["id"])}
    plain = [q for q in questions if not (q.get("setup_script") or q.get("turns") or q.get("session") == "token")]
    errors: list[str] = []

    def ask(q: dict, text: str | None = None) -> None:
        try:
            _turns(agent, Session("perf_" + q["id"], "perf", "", anonymous=True), [text or q["question"]],
                   q.get("as_of"), q.get("belief_at"))
        except Exception as e:  # noqa: BLE001 - a failing question is reported, the run goes on
            errors.append(f"{q['id']}: {type(e).__name__}: {e}"[:200])

    PHASE[0] = "questions"
    for q in plain:
        ask(q)
    kinds = ("system:", "team:", "person:")
    ids = [i for i in sorted(names) if i.startswith(kinds)]
    people = [i for i in ids if i.startswith("person:")]
    systems = [i for i in ids if i.startswith("system:")]
    extra = [t.format(s=names[s], p=names[p]) for s, p in zip(systems[:5], people[:5])
             for t in ("Who should I ask about {s}?", "How is {p} connected to {s}?", "Who owned {s} before?",
                       "What is {p}'s primary team?")]
    for i, text in enumerate(extra):
        ask({"id": f"extra{i}"}, text)
    if scale > 1:
        PHASE[0] = "questions_clone"
        for q in plain[::10]:
            ask(q, _rename(q["question"], names, scale))

    PHASE[0] = "panels"
    as_of = min(q["as_of"] for q in questions if q.get("as_of"))
    integrity.check(g, deep=True)
    app.names(",".join(ids[:20]))
    app._default_identity()
    sample = ids + ([_cid(i, scale) for i in ids] if scale > 1 else [])
    for _ in range(reps):
        app.overview()
        app.directory()
        app.graph()
        app.people()
    for t in (None, as_of):
        app.overview(as_of=t)
        app.directory(as_of=t)
        app.graph(as_of=t)
    for eid in sample:
        app.entity_panel(eid)
        app.neighbourhood(eid)
    for eid in ids[:10]:
        app.entity_panel(eid, as_of=as_of)
    for pid in [i for i in ids if i.startswith("person:")][:10]:
        app.pending(pid)
    for r in g.ro("MATCH (s:Source) WHERE s.kind <> 'world_meta' RETURN s.id AS id ORDER BY id LIMIT 20"):
        app.get_source(r["id"])
    for r in g.ro("MATCH (s:Span) RETURN s.id AS id ORDER BY id LIMIT 20"):
        app.get_span(r["id"])

    PHASE[0] = "tools"
    args = {"critical_systems": {}, "key_people": {}, "knowledge_gaps": {},
            "connection_between": {"from_id": people[0], "to_id": _cid(systems[0], scale) if scale > 1 else systems[0]}}
    tool_ms: dict[str, list[float]] = defaultdict(list)
    for name in ALGO:
        run_tool(Ctx(g, now=now_ms()), name, args[name])   # warm the snapshot
        for _ in range(reps):
            t0 = time.perf_counter()
            run_tool(Ctx(g, now=now_ms()), name, args[name])
            tool_ms[name].append((time.perf_counter() - t0) * 1000)

    PHASE[0] = "rebuild"
    rebuild_s = []
    main_now = now_ms()
    version = snapshot._fingerprint(g)
    for _ in range(5):
        snap = Graph(name=f"{g.name}__snap_perfbuild", host=g.host, port=g.port)
        snap.delete()
        t0 = time.perf_counter()
        snapshot.build(g, snap, main_now, version)
        rebuild_s.append(time.perf_counter() - t0)
        snap.delete()

    PHASE[0] = "sessions"
    world = World.load(SEED)
    for q in [q for q in questions if q not in plain]:
        try:
            if q.get("setup_script"):
                q = resolve(q, run_setup(g, q["setup_script"], world))
                if q.get("setup_failed"):
                    errors.append(f"{q['id']}: setup failed {q['setup_failed']}"[:200])
                    continue
            s = agent.create_session("perf_" + q["id"], q.get("acting_as") or "")
            _turns(agent, s, list(q.get("turns") or [q["question"]]), q.get("as_of"), q.get("belief_at"))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{q['id']}: {type(e).__name__}: {e}"[:200])

    PHASE[0] = "ingest"
    text = "# Perf notes\n\n" + "\n\n".join(f"{n} depends on {m} for nightly reports." for n, m in
                                           zip([names[s] for s in systems[:5]], [names[s] for s in systems[5:10]]))
    Ingestor(g).ingest_upload("perf-notes.md", text.encode())
    return {"tool_ms": dict(tool_ms), "rebuild_s": rebuild_s, "errors": errors,
            "questions": len(questions) + len(extra) + (len(plain[::10]) if scale > 1 else 0)}


# Report

def pct(xs: list[float], p: float) -> float:
    s = sorted(xs)
    return s[max(0, math.ceil(p * len(s)) - 1)]


def stats(xs: list[float]) -> dict:
    return {"n": len(xs), "p50": round(pct(xs, 0.5), 1), "p95": round(pct(xs, 0.95), 1), "max": round(max(xs), 1)}


def template_stats(samples: list[dict]) -> dict[str, dict]:
    names = set(templates.all_names())
    by: dict[str, list[float]] = defaultdict(list)
    for s in samples:
        if s["kind"] == "read" and s["phase"] != "build" and s["template"] in names:
            by[s["template"]].append(s["ms"])
    return {t: stats(v) for t, v in sorted(by.items())}


def profile(samples: list[dict], name: str, port: int) -> str:
    worst = max((s for s in samples if s["template"] == name and s["kind"] == "read" and s["phase"] != "build"),
                key=lambda s: s["ms"])
    g = Graph(name=worst["graph"], port=port)
    try:
        out = g.raw("GRAPH.PROFILE", worst["graph"], with_params(worst["cypher"], worst["params"]))
    except Exception as e:  # noqa: BLE001
        return f"PROFILE failed: {e}"
    lines = out if isinstance(out, list) else [out]
    return "\n".join(x.decode() if isinstance(x, bytes) else str(x) for x in lines)


def run_one(version: str, scale: int, questions: list[dict], reps: int) -> dict:
    port = PORTS[version]
    g = Graph(name=f"perf_x{scale}", port=port)
    if g.module_version() != MODULE[version]:
        raise RuntimeError(f"port {port} is not FalkorDB {version}")
    SAMPLES.clear()
    build = build_world(g, scale)
    work = workload(g, scale, questions, reps)
    tstats = template_stats(SAMPLES)
    slow = sorted(tstats, key=lambda t: -tstats[t]["p95"])[:5]
    profiles = {t: profile(SAMPLES, t, port) for t in slow} if scale > 1 else {}
    writes = [s["ms"] for s in SAMPLES if s["kind"] == "write" and s["template"] == "write_plan" and s["phase"] != "build"]
    snapshot.drop_all(g)
    g.delete()
    return {"version": version, "scale": scale, "build": build, "templates": tstats,
            "tools": {t: stats(v) for t, v in work["tool_ms"].items()},
            "rebuild": {"runs_s": [round(x, 3) for x in work["rebuild_s"]], "p50_s": round(pct(work["rebuild_s"], .5), 3),
                        "max_s": round(max(work["rebuild_s"]), 3)},
            "write_plan": stats(writes) if writes else None,
            "unexercised": sorted(set(templates.all_names()) - set(tstats)),
            "slowest": slow, "profiles": profiles, "errors": work["errors"], "questions": work["questions"]}


def markdown(runs: list[dict], head: str) -> str:
    out = [f"# Graph performance ({head})", "",
           "Client-side ms per query as `brain.db.Graph` logs it (QueryLog), so every number includes the network "
           "round trip to FalkorDB in local Docker; tool and rebuild times are wall-clock around the call. "
           "Offline (`BRAIN_LLM=off`). World and workload: see the `evals/perf.py` docstring. p95 is nearest-rank, "
           "so with a small n it is close to the max and sensitive to other load on the host. PROFILE runs once per "
           "template after the workload, on its slowest call's parameters (the graph then also holds the "
           "workload's sessions and actions).", "",
           "## Targets at 10x", "", "| Version | Target | Result | Met |", "|---|---|---|---|"]
    for r in runs:
        if r["scale"] == 1:
            continue
        worst = max(r["templates"].items(), key=lambda kv: kv[1]["p95"])
        over = [t for t, s in r["templates"].items() if s["p95"] > TARGET["template_p95"]]
        out.append(f"| {r['version']} | every read template p95 <= 50 ms | worst {worst[0]} {worst[1]['p95']} ms"
                   f"{'; over: ' + ', '.join(over) if over else ''} | {'met' if not over else 'missed'} |")
        out.append(f"| {r['version']} | snapshot rebuild <= 2 s | max {r['rebuild']['max_s']} s (p50 "
                   f"{r['rebuild']['p50_s']} s) | {'met' if r['rebuild']['max_s'] <= TARGET['rebuild_s'] else 'missed'} |")
        tw = max(r["tools"].items(), key=lambda kv: kv[1]["p95"])
        tover = [t for t, s in r["tools"].items() if s["p95"] > TARGET["tool_p95"]]
        out.append(f"| {r['version']} | algorithm tools p95 <= 200 ms | worst {tw[0]} {tw[1]['p95']} ms | "
                   f"{'met' if not tover else 'missed'} |")
    for r in runs:
        b = r["build"]
        out += ["", f"## FalkorDB {r['version']}, scale {r['scale']}x", "",
                f"Graph: {b['nodes']} nodes, {b['edges']} edges ({b['entities']} entities, {b['assertions']} "
                f"assertions, {b['spans']} spans); built in {b['total_s']} s. Workload: {r['questions']} questions"
                f"{', ' + str(len(r['errors'])) + ' errors' if r['errors'] else ''}.", "",
                "| Algorithm tool | n | p50 ms | p95 ms | max ms |", "|---|---|---|---|---|"]
        out += [f"| {t} | {s['n']} | {s['p50']} | {s['p95']} | {s['max']} |" for t, s in r["tools"].items()]
        out += ["", f"Snapshot rebuild, cold, 5 runs: {', '.join(str(x) for x in r['rebuild']['runs_s'])} s.", ""]
        if r["write_plan"]:
            w = r["write_plan"]
            out += [f"Guarded write (`write_plan`, not a target): n {w['n']}, p50 {w['p50']} ms, p95 {w['p95']} ms.", ""]
        out += ["| Template | n | p50 ms | p95 ms | max ms |", "|---|---|---|---|---|"]
        out += [f"| {t} | {s['n']} | {s['p50']} | {s['p95']} | {s['max']} |"
                for t, s in sorted(r["templates"].items(), key=lambda kv: -kv[1]["p95"])]
        if r["errors"]:
            out += ["", "Errors:", ""] + [f"- {e}" for e in r["errors"]]
        for t, p in r["profiles"].items():
            out += ["", f"### PROFILE {t} ({r['version']}, {r['scale']}x)", "", "```", p, "```"]
    unex = sorted(set.intersection(*[set(r["unexercised"]) for r in runs])) if runs else []
    out += ["", "## Templates not exercised by the workload", "", ", ".join(unex) or "none", ""]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(prog="evals.perf")
    ap.add_argument("--scale", type=int, nargs="+", default=[1, 10])
    ap.add_argument("--versions", nargs="+", default=list(PORTS))
    ap.add_argument("--questions", required=True, help="questions-seed1.jsonl from an eval results folder")
    ap.add_argument("--reps", type=int, default=20)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    questions = [json.loads(line) for line in Path(a.questions).read_text().splitlines() if line.strip()]
    runs = [run_one(v, s, questions, a.reps) for v in a.versions for s in a.scale]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "perf.json").write_text(json.dumps(runs, indent=1, default=str))
    (out / "perf.md").write_text(markdown(runs, out.name))
    print(markdown(runs, out.name))


if __name__ == "__main__":
    main()
