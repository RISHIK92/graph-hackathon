"""Snapshot graphs for FalkorDB's algo.* procedures (item 17).

The procedures filter by node label and relationship type only, never by property, so on the main graph they
would also count edges outside their validity window (historical owners), and every main-graph node shares
:Entity. A snapshot graph `<graph>__snap_<day|now>` holds just the entity-to-entity edges live at V, with kind
labels, plus derived TOUCHES {w} edges (spans a person authored that mention an entity). It is derived and
read-only: rebuilt when the main graph's write fingerprint changes, never on the guarded write path, and it
holds no facts; every edge carries the `aid` of the main-graph fact it mirrors, so answers cite the main graph.
"""
from __future__ import annotations

import time

from .db import Graph, WriteMismatch
from .write_path import now_ms

KIND = {"person": "Person", "team": "Team", "system": "System", "decision": "Decision", "project": "Project",
        "ticket": "Ticket"}
EDGE_TYPES = ("OWNS", "LEADS", "MEMBER_OF", "DEPENDS_ON", "WORKS_ON", "PART_OF", "AFFECTS", "DECIDED_BY",
              "ASSIGNED_TO", "ABOUT")
# Betweenness counts directed paths, and people only have outgoing edges, so it runs over LINK: one edge each
# way for every connection between people, teams and systems (never cited; the facts are the typed edges).
LINKED = ("OWNS", "LEADS", "MEMBER_OF", "DEPENDS_ON", "WORKS_ON")
DAY = 86_400_000
KEEP = 4   # "now" plus a few as-of days


def name_for(main: Graph, as_of: int | None) -> str:
    return f"{main.name}__snap_" + ("now" if as_of is None else time.strftime("%Y%m%d", time.gmtime(as_of / 1000)))


def _fingerprint(main: Graph) -> str:
    r = main.q("snapshot_version")[0]
    return f"{r['n']}:{r['last']}:{r['gone']}:{r['actions']}"


def snapshot(main: Graph, as_of: int | None = None, now: int | None = None) -> Graph:
    """The snapshot graph for V (as_of rounded to the end of its UTC day, or now), built if missing or stale."""
    snap = Graph(name=name_for(main, as_of), host=main.host, port=main.port)
    version = _fingerprint(main)
    try:
        meta = snap.q("snap_meta")
    except Exception:  # noqa: BLE001 - no snapshot graph yet
        meta = []
    if meta and meta[0]["version"] == version:
        return snap
    V = (as_of // DAY) * DAY + DAY - 1 if as_of is not None else (now or now_ms())
    build(main, snap, V, version)
    _evict(main)
    return snap


def build(main: Graph, snap: Graph, V: int, version: str) -> None:
    snap.delete()
    nodes = [n for n in main.q("graph_nodes", timeout=10000)
             if n["id"].split(":")[0] in KIND and not (n.get("decided_at") and n["decided_at"] > V)]
    have = {n["id"] for n in nodes}
    edges = [e for e in main.q("graph_edges", {"V": V}, timeout=10000)
             if e["type"] in EDGE_TYPES and e["source"] in have and e["target"] in have]
    touches = [t for t in main.q("snapshot_touches", {"V": V}, timeout=10000) if t["person"] in have and t["target"] in have]
    snap.write("CREATE INDEX FOR (n:N) ON (n.id)", template="snapshot_build")
    # F26: 4.22.0's algo.betweenness rejects a relationship type the graph has never had (6.0.1 accepts it), so
    # every type is registered up front, as schema.create does for F23.
    snap.write("CREATE (a) " + " ".join(f"CREATE (a)-[:{t}]->(a)" for t in (*EDGE_TYPES, "TOUCHES", "LINK")) +
               " WITH a DETACH DELETE a", template="snapshot_build")
    for prefix, label in KIND.items():
        rows = [{"id": n["id"], "name": n["name"]} for n in nodes if n["id"].startswith(prefix + ":")]
        if rows:   # the label is from KIND, never from data
            _check(snap.write(f"UNWIND $rows AS r CREATE (:N:{label} {{id:r.id, name:r.name}})", {"rows": rows},
                              template="snapshot_build"), "nodes_created", len(rows))
    for t in EDGE_TYPES:
        rows = [{"s": e["source"], "t": e["target"], "aid": e["aid"]} for e in edges if e["type"] == t]
        if rows:
            _check(snap.write(f"UNWIND $rows AS r MATCH (a:N {{id:r.s}}) MATCH (b:N {{id:r.t}}) "
                              f"CREATE (a)-[:{t} {{aid:r.aid}}]->(b)", {"rows": rows}, template="snapshot_build"),
                   "relationships_created", len(rows))
    if touches:
        _check(snap.write("UNWIND $rows AS r MATCH (a:N {id:r.person}) MATCH (b:N {id:r.target}) "
                          "CREATE (a)-[:TOUCHES {w:r.w}]->(b)", {"rows": touches}, template="snapshot_build"),
               "relationships_created", len(touches))
    pairs = [{"s": e["source"], "t": e["target"]} for e in edges if e["type"] in LINKED]
    pairs += [{"s": t["person"], "t": t["target"]} for t in touches]
    if pairs:
        _check(snap.write("UNWIND $rows AS r MATCH (a:N {id:r.s}) MATCH (b:N {id:r.t}) "
                          "CREATE (a)-[:LINK]->(b), (b)-[:LINK]->(a)", {"rows": pairs}, template="snapshot_build"),
               "relationships_created", 2 * len(pairs))
    snap.write("CREATE (:Meta {version:$v, V:$V, built_at:$t})", {"v": version, "V": V, "t": now_ms()},
               template="snapshot_build")


def _check(res, counter: str, want: int) -> None:
    """A build write that creates fewer nodes or edges than rows is a failure (the F18 rule, for derived data)."""
    if res.counters[counter] != want:
        raise WriteMismatch(f"snapshot build: {counter} {res.counters[counter]} != {want}")


def snapshots(main: Graph) -> list[str]:
    names = main.raw("GRAPH.LIST")
    return sorted(n.decode() if isinstance(n, bytes) else n for n in names
                  if (n.decode() if isinstance(n, bytes) else n).startswith(f"{main.name}__snap_"))


def _evict(main: Graph) -> None:
    dated = [n for n in snapshots(main) if not n.endswith("__snap_now")]
    for n in dated[:max(0, len(dated) - (KEEP - 1))]:   # the oldest days go first
        Graph(name=n, host=main.host, port=main.port).delete()


def drop_all(main: Graph) -> None:
    """/admin/reset and test teardown: snapshot graphs are derived, so they go with the main graph."""
    for n in snapshots(main):
        Graph(name=n, host=main.host, port=main.port).delete()
