"""Day-one probe suite (07 §5): re-run the spec's findings F1–F18 and the practice findings F19–F22 on a
FalkorDB instance and report what holds. Each probe returns {"id", "expect", "observed", "ok"}."""
from __future__ import annotations

import time
import uuid

from brain.config import MAX
from brain.db import Graph, GuardFailed

PROBES = []


def probe(pid: str, expect: str):
    def deco(fn):
        PROBES.append((pid, expect, fn))
        return fn
    return deco


def _q(g: Graph, q: str, p: dict | None = None):
    return g.write(q, p or {}, template="probe")


@probe("F1", "runtime error rolls back earlier CREATEs")
def f1(g):
    try:
        _q(g, "CREATE (:P {id:'f1'}) WITH 1 AS x RETURN 1/0")
    except Exception:
        pass
    return g.ro("MATCH (p:P {id:'f1'}) RETURN count(p) AS n")[0]["n"] == 0


@probe("F2", "EXISTS {} doesn't parse; pattern predicates work")
def f2(g):
    _q(g, "CREATE (:P {id:'a'})-[:X]->(:P {id:'b'})")
    try:
        g.ro("MATCH (a:P) WHERE EXISTS { (a)-[:X]->() } RETURN a")
        exists_ok = True
    except Exception:
        exists_ok = False
    pp = g.ro("MATCH (a:P) WHERE (a)-[:X]->() RETURN a.id AS id")
    return (not exists_ok) and [r["id"] for r in pp] == ["a"]


@probe("F5", "no per-query efRuntime (5-arg queryNodes rejected)")
def f5(g):
    try:
        g.ro("CALL db.idx.vector.queryNodes('P','e',1,vecf32([0.1,0.2]), 50) YIELD node RETURN node")
        return False
    except Exception:
        return True


@probe("F6", "typed 3-hop traversal is cheap (ms, small graph)")
def f6(g):
    _q(g, "UNWIND range(1,150) AS i CREATE (:E {id:i})")
    _q(g, "MATCH (a:E),(b:E) WHERE b.id = a.id + 1 CREATE (a)-[:OWNS {valid_to:$m}]->(b)", {"m": MAX})
    t0 = time.perf_counter()
    g.ro("MATCH p=(a:E {id:1})-[:OWNS|DEPENDS_ON*1..3]->(b) RETURN count(p)")
    return round((time.perf_counter() - t0) * 1000, 2)


@probe("F12", "two filtered comprehensions in one projection (6.0.1: first is empty)")
def f12(g):
    _q(g, "CREATE (k:K {id:'k'})<-[:OWNS {v:1}]-(t:T {id:'t'})<-[:LEADS {v:1}]-(p:Pp {id:'person:pr'}), "
          "(k)<-[:OWNS {v:1}]-(:Pp {id:'person:x'})")
    r = g.ro("MATCH (k:K {id:'k'}) WITH k, [(k)<-[o:OWNS]-(t)<-[l:LEADS]-(p) WHERE o.v = 1 AND l.v = 1 | p.id] AS e1, "
             "[(k)<-[o2:OWNS]-(p2) WHERE p2.id STARTS WITH 'person:' | p2.id] AS e2 RETURN e1")
    return r[0]["e1"]


@probe("F13", "uncorrelated CALL {} returns nothing on 6.0.1")
def f13(g):
    _q(g, "CREATE (:K {id:'k2'}), (:Pq {id:'p'})-[:LEADS]->(:Tq {id:'t'})")
    r = g.ro("MATCH (k:K {id:'k2'}) CALL { MATCH (p:Pq)-[:LEADS]->(t) RETURN collect(p.id) AS a } RETURN a")
    return r[0]["a"] if r else None


@probe("F14", "pattern comprehension inside WHERE (4.22 fails)")
def f14(g):
    _q(g, "CREATE (:W {id:'w'})")
    try:
        g.ro("MATCH (a:W) WHERE size([(a)-[:X]->(b) | b]) = 0 RETURN a.id")
        return "works"
    except Exception as e:
        return f"fails: {str(e)[:60]}"


@probe("F16", "pattern predicate in WHERE then MATCH (6.0.1 fails to compile)")
def f16(g):
    _q(g, "CREATE (a:Q {id:'q'})-[:OBJECT]->(:Sy {id:'s1'}), (a)-[:SUBJECT]->(:O {id:'o'})")
    try:
        r = g.ro("MATCH (a)-[:OBJECT]->(:Sy {id:'s1'}) WHERE NOT (a)<-[:SUPERSEDES]-() MATCH (a)-[:SUBJECT]->(o) "
                 "RETURN o.id AS o")
        return f"works: {r}"
    except Exception as e:
        return f"fails: {str(e)[:60]}"


@probe("F17", "sentinel guard aborts and rolls back; conditional 1/0 behaviour")
def f17(g):
    try:
        g.write("CREATE (:GuardFail {id:'sentinel'})")
    except Exception:
        pass
    try:
        g.write("CREATE (:P {id:'f17'}) WITH 1 AS x FOREACH (_ IN CASE WHEN false THEN [] ELSE [1] END | "
                "CREATE (:GuardFail {id:'sentinel'}))")
        aborted = False
    except GuardFailed:
        aborted = True
    rolled = g.ro("MATCH (p:P {id:'f17'}) RETURN count(p) AS n")[0]["n"] == 0
    try:
        g.ro("RETURN CASE WHEN true THEN 1 ELSE 1/0 END AS x")
        cond = "untaken branch not evaluated"
    except Exception:
        cond = "untaken branch evaluated (aborts)"
    return {"sentinel_aborts": aborted, "rolled_back": rolled, "case_1_over_0": cond}


@probe("F18", "a guard whose MATCH finds nothing returns zero rows silently")
def f18(g):
    r = g.write("MATCH (n:Nope {id:'x'}) SET n.y = 1 RETURN n")
    return {"rows": len(r.rows), "props_set": r.counters["properties_set"]}


@probe("F19", "more than ~6 unit CALL {} subqueries mis-resolve variables (6.0.1)")
def f19(g):
    _q(g, "CREATE (:C {id:'c'})")
    triv = "CALL { WITH ok MATCH (c:C {id:'c'}) SET c.t = 1 } "
    tgt = "CALL { WITH ok UNWIND [1] AS x MATCH (s:C {id:'c'}) SET s.z = x } "
    out = {}
    for k in (5, 7):
        try:
            g.write("WITH 1 AS ok " + triv * k + tgt + "RETURN ok")
            out[k] = "ok"
        except Exception as e:
            out[k] = str(e)[:50]
    return out


@probe("F21", "UNWIND + two MATCH after count(*) silently drops rows (6.0.1)")
def f21(g):
    pre = "CREATE (:Cc {id:'c1'}) WITH count(*) AS _a UNWIND $l AS x CREATE (n:Aa) SET n += x WITH count(*) AS _b "
    q1 = pre + "UNWIND $l AS y MATCH (a:Aa {id:y.id}) MATCH (c:Cc {id:y.c}) CREATE (a)-[:R]->(c) RETURN 1"
    r1 = g.write(q1, {"l": [{"id": "a", "c": "c1"}]}).counters["relationships_created"]
    _q(g, "MATCH (n:Aa) DETACH DELETE n")
    _q(g, "MATCH (n:Cc) DETACH DELETE n")
    q2 = pre + "UNWIND $l AS y WITH y MATCH (a:Aa {id:y.id}) MATCH (c:Cc {id:y.c}) CREATE (a)-[:R]->(c) RETURN 1"
    r2 = g.write(q2, {"l": [{"id": "a", "c": "c1"}]}).counters["relationships_created"]
    return {"plain_rels": r1, "with_y_workaround_rels": r2}


def run_all(port: int) -> dict:
    out = {"port": port, "results": []}
    for pid, expect, fn in PROBES:
        g = Graph(name=f"probe_{uuid.uuid4().hex[:6]}", port=port)
        try:
            out.setdefault("module", g.module_version())
            g.write("CREATE INDEX FOR (n:GuardFail) ON (n.id)")
            g.raw("GRAPH.CONSTRAINT", "CREATE", g.name, "UNIQUE", "NODE", "GuardFail", "PROPERTIES", "1", "id")
            time.sleep(0.05)
            obs = fn(g)
        except Exception as e:  # noqa: BLE001
            obs = f"error: {e}"
        finally:
            g.delete()
        out["results"].append({"id": pid, "expect": expect, "observed": obs})
    return out


if __name__ == "__main__":
    import json
    import sys
    for p in (sys.argv[1:] or ["6391", "6392"]):
        print(json.dumps(run_all(int(p)), indent=1, default=str))
