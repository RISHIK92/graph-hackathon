"""Indexes, constraints, the guard sentinel and startup checks (01 §6, README A51)."""
from __future__ import annotations

import time

from .config import settings
from .db import Graph
from .registry import PROJECTION_TYPES

NODE_LABELS = ["Source", "Span", "Assertion", "Chain", "Action", "Entity",
               "Person", "Team", "Project", "System", "Decision", "Ticket", "GuardFail"]

RANGE_INDEXES = [
    ("Source", "doc_key"), ("Source", "is_latest"), ("Source", "user_id"),
    ("Assertion", "chain_id"), ("Assertion", "run_id"), ("Assertion", "key_id"),
    ("Assertion", "predicate"), ("Assertion", "subject_id"), ("Assertion", "object_id"),
    ("Assertion", "valid_to"), ("Assertion", "recorded_at"), ("Span", "doc_key"),
    ("Entity", "aliases"),
]

REL_TYPES = sorted(set(PROJECTION_TYPES) | {
    "HAS_SPAN", "NEXT", "REVISES", "MENTIONS", "AUTHORED_BY", "HAS_SOURCE", "OF_CHAIN", "SUBJECT", "OBJECT",
    "EVIDENCED_BY", "SUPERSEDES", "CONTINUES", "DISPUTES", "CONFIRMS", "MOTIVATED_BY", "BASED_ON", "PRODUCED",
    "TARGETS", "IN_SESSION"})


def _try(g: Graph, q: str) -> None:
    try:
        g.write(q, template="schema")
    except Exception as e:  # noqa: BLE001
        if "already indexed" not in str(e).lower() and "already exists" not in str(e).lower():
            raise


def create(g: Graph) -> None:
    for label in NODE_LABELS:
        _try(g, f"CREATE INDEX FOR (n:{label}) ON (n.id)")
    for label, prop in RANGE_INDEXES:
        _try(g, f"CREATE INDEX FOR (n:{label}) ON (n.{prop})")
    for rel in PROJECTION_TYPES:
        _try(g, f"CREATE INDEX FOR ()-[r:{rel}]-() ON (r.valid_to)")
    _try(g, "CREATE FULLTEXT INDEX FOR (n:Span) ON (n.text, n.keys)")
    _try(g, "CREATE FULLTEXT INDEX FOR (n:Entity) ON (n.name, n.aliases_text, n.description)")
    d = settings.embed_dim
    for label in ("Span", "Entity"):
        _try(g, f"CREATE VECTOR INDEX FOR (n:{label}) ON (n.embedding) OPTIONS "
                f"{{dimension:{d}, similarityFunction:'cosine', M:16, efConstruction:200, efRuntime:100}}")
    for label in NODE_LABELS:
        try:
            g.raw("GRAPH.CONSTRAINT", "CREATE", g.name, "UNIQUE", "NODE", label, "PROPERTIES", "1", "id")
        except Exception as e:  # noqa: BLE001
            if "already exists" not in str(e).lower():
                raise
    wait_constraints(g)
    g.write("MERGE (:GuardFail {id:'sentinel'})", template="schema")
    # 4.22.0 caches a pattern comprehension compiled before its relationship type exists as always
    # empty, even after edges of that type appear (practice finding F23). Register every type up front.
    g.write("CREATE (a) " + " ".join(f"CREATE (a)-[:{t}]->(a)" for t in REL_TYPES) +
            " WITH a DETACH DELETE a", template="schema")


def wait_constraints(g: Graph, timeout_s: float = 60) -> None:
    deadline = time.time() + timeout_s
    while True:
        rows = g.ro("CALL db.constraints() YIELD type, label, properties, status "
                    "RETURN type, label, properties, status", template="schema")
        bad = [r for r in rows if r["status"] == "FAILED"]
        if bad:
            raise RuntimeError(f"constraint FAILED: {bad}")
        if all(r["status"] == "OPERATIONAL" for r in rows):
            return
        if time.time() > deadline:
            raise RuntimeError("constraints not OPERATIONAL in time")
        time.sleep(0.2)


def configure_timeouts(g: Graph) -> None:
    """F9: the server ships with the deprecated TIMEOUT 1000; set the new pair explicitly."""
    for k, v in (("TIMEOUT_DEFAULT", settings.timeout_default), ("TIMEOUT_MAX", settings.timeout_max)):
        try:
            g.raw("GRAPH.CONFIG", "SET", k, str(v))
        except Exception:  # noqa: BLE001 - not settable at runtime on this version
            pass


def health(g: Graph, expect_pin: int | None = None) -> dict:
    out: dict = {"reachable": False}
    try:
        out["module_version"] = g.module_version()
        out["reachable"] = True
        out["pin_ok"] = expect_pin is None or out["module_version"] == expect_pin
        rows = g.ro("CALL db.constraints() YIELD status RETURN status", template="health")
        out["constraints_operational"] = bool(rows) and all(r["status"] == "OPERATIONAL" for r in rows)
        s = g.ro("MATCH (s:GuardFail {id:'sentinel'}) RETURN count(s) AS n", template="health")
        out["sentinel"] = s[0]["n"] == 1
        out["ok"] = out["pin_ok"] and out["constraints_operational"] and out["sentinel"]
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)
        out["ok"] = False
    return out


def reset(g: Graph) -> None:
    g.delete()
    create(g)
