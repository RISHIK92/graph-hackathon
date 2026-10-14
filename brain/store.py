"""Provenance-layer writes: entities, Sources, Spans, HAS_SPAN, NEXT, MENTIONS, AUTHORED_BY.

These never touch Assertions, evidence or projections; those go through write_path.
"""
from __future__ import annotations

from .config import MAX
from .db import Graph

ENTITY_LABELS = {"person": "Person", "team": "Team", "project": "Project", "system": "System",
                 "decision": "Decision", "ticket": "Ticket"}


def upsert_entities(g: Graph, entities: list[dict]) -> None:
    """entities: {id, name, aliases[], description?, embedding?, created_from, ...extra}."""
    by_label: dict[str, list[dict]] = {}
    for e in entities:
        lab = ENTITY_LABELS[e["id"].split(":", 1)[0]]
        props = {k: v for k, v in e.items() if v is not None}
        props.setdefault("aliases", [])
        props["aliases"] = sorted({a.lower() for a in [e.get("name", ""), *props["aliases"]] if a})
        props["aliases_text"] = " ".join(props["aliases"])
        props.setdefault("description", "")
        by_label.setdefault(lab, []).append(props)
    for lab, rows in by_label.items():
        for i in range(0, len(rows), 200):
            g.write(f"UNWIND $rows AS x MERGE (n:Entity:{lab} {{id:x.id}}) SET n += x",
                    {"rows": rows[i:i + 200]}, template="upsert_entities")


def source_exists(g: Graph, sid: str) -> dict | None:
    r = g.ro("MATCH (s:Source {id:$id}) RETURN s.ingested_at AS ingested_at, s.is_latest AS is_latest",
             {"id": sid}, template="source_exists")
    return r[0] if r else None


def create_source(g: Graph, props: dict) -> None:
    g.write("MERGE (s:Source {id:$id}) ON CREATE SET s += $p", {"id": props["id"], "p": props}, template="create_source")


def set_source(g: Graph, sid: str, props: dict) -> None:
    g.write("MATCH (s:Source {id:$id}) SET s += $p", {"id": sid, "p": props}, template="set_source")


def revisions(g: Graph, doc_key: str) -> list[dict]:
    return g.ro("MATCH (s:Source {doc_key:$k}) RETURN s.id AS id, s.updated_at AS updated_at, "
                "s.is_latest AS is_latest, s.ingested_at AS ingested_at, s.status AS status",
                {"k": doc_key}, template="revisions")


def link_revision(g: Graph, newer: str, older: str) -> None:
    g.write("MATCH (n:Source {id:$n}) MATCH (o:Source {id:$o}) MERGE (n)-[:REVISES]->(o)",
            {"n": newer, "o": older}, template="revises")


def existing_spans(g: Graph, span_ids: list[str]) -> dict[str, dict]:
    rows = g.ro("UNWIND $ids AS i MATCH (s:Span {id:i}) RETURN s.id AS id, s.ts AS ts",
                {"ids": span_ids}, template="existing_spans")
    return {r["id"]: r for r in rows}


def upsert_spans(g: Graph, source_id: str, spans: list[dict], latest: bool, now: int | None = None) -> None:
    """spans: {id, doc_key, text, keys, ts, author_id, author_role, kind, embedding?, embed_model,
    char_start, char_end, ordinal, heading_path}. Existing spans get only a HAS_SPAN edge and a
    lowered ts (A58)."""
    rows = []
    for s in spans:
        node = {k: s[k] for k in ("id", "doc_key", "text", "keys", "ts", "author_id", "author_role",
                                  "kind", "embed_model") if k in s}
        rows.append({"node": node, "id": s["id"], "ts": s["ts"], "cs": s["char_start"], "ce": s["char_end"],
                     "ord": s["ordinal"], "hp": s.get("heading_path", ""), "emb": s.get("embedding")})
    rm = MAX if latest else 0  # a late older revision's HAS_SPAN edges are written closed (01 §5)
    for i in range(0, len(rows), 100):
        chunk = rows[i:i + 100]
        g.write(
            "UNWIND $rows AS x "
            "MERGE (s:Span {id:x.id}) "
            "ON CREATE SET s += x.node "
            "ON MATCH SET s.ts = CASE WHEN x.ts < s.ts THEN x.ts ELSE s.ts END "
            "WITH s, x "
            "MATCH (src:Source {id:$src}) "
            "MERGE (src)-[h:HAS_SPAN]->(s) "
            "ON CREATE SET h.char_start = x.cs, h.char_end = x.ce, h.ordinal = x.ord, "
            "h.heading_path = x.hp, h.recorded_at = $now, h.removed_at = $rm",
            {"rows": chunk, "src": source_id, "now": _now() if now is None else now, "rm": rm}, template="upsert_spans")
    # vecf32 embeddings are set separately so the MERGE map stays plain
    emb = [{"id": r["id"], "e": r["emb"]} for r in rows if r["emb"] is not None]
    for i in range(0, len(emb), 100):
        g.write("UNWIND $rows AS x MATCH (s:Span {id:x.id}) WHERE s.embedding IS NULL "
                "SET s.embedding = vecf32(x.e)", {"rows": emb[i:i + 100]}, template="span_embeddings")


def set_next_chain(g: Graph, doc_key: str, ordered_ids: list[str]) -> None:
    g.write("MATCH (a:Span {doc_key:$k})-[n:NEXT]->() DELETE n", {"k": doc_key}, template="next_clear")
    pairs = [{"a": a, "b": b} for a, b in zip(ordered_ids, ordered_ids[1:]) if a != b]
    for i in range(0, len(pairs), 200):
        g.write("UNWIND $p AS x MATCH (a:Span {id:x.a}) MATCH (b:Span {id:x.b}) "
                "CREATE (a)-[:NEXT {doc_key:$k}]->(b)", {"p": pairs[i:i + 200], "k": doc_key}, template="next_set")


def close_has_span(g: Graph, source_id: str, now: int) -> None:
    g.write("MATCH (:Source {id:$s})-[h:HAS_SPAN]->() WHERE h.removed_at = $max SET h.removed_at = $now",
            {"s": source_id, "max": MAX, "now": now}, template="close_has_span")


def open_has_span(g: Graph, source_id: str, now: int) -> None:
    g.write("MATCH (:Source {id:$s})-[h:HAS_SPAN]->() SET h.recorded_at = $now, h.removed_at = $max",
            {"s": source_id, "max": MAX, "now": now}, template="open_has_span")


def add_mentions(g: Graph, mentions: list[dict]) -> None:
    """{span_id, entity_id, start, end, method, hedged}"""
    for i in range(0, len(mentions), 200):
        g.write("UNWIND $m AS x MATCH (s:Span {id:x.span_id}) MATCH (e:Entity {id:x.entity_id}) "
                "MERGE (s)-[r:MENTIONS {start:x.start, end:x.end}]->(e) "
                "ON CREATE SET r.method = x.method, r.hedged = x.hedged",
                {"m": mentions[i:i + 200]}, template="mentions")


def add_authored_by(g: Graph, pairs: list[dict]) -> None:
    for i in range(0, len(pairs), 200):
        g.write("UNWIND $p AS x MATCH (s:Span {id:x.span_id}) MATCH (p:Person {id:x.person_id}) "
                "MERGE (s)-[:AUTHORED_BY]->(p)", {"p": pairs[i:i + 200]}, template="authored_by")


def add_has_source(g: Graph, ticket_id: str, source_id: str) -> None:
    g.write("MATCH (t:Ticket {id:$t}) MATCH (s:Source {id:$s}) MERGE (t)-[:HAS_SOURCE]->(s)",
            {"t": ticket_id, "s": source_id}, template="has_source")


def add_motivated_by(g: Graph, decision_id: str, span_id: str, section: str, now: int) -> None:
    g.write("MATCH (d:Decision {id:$d}) MATCH (s:Span {id:$s}) "
            "MERGE (d)-[m:MOTIVATED_BY {section:$sec, action_id:''}]->(s) "
            "ON CREATE SET m.recorded_at = $now, m.removed_at = $max",
            {"d": decision_id, "s": span_id, "sec": section, "now": now, "max": MAX}, template="motivated_by")


def _now() -> int:
    import time
    return int(time.time() * 1000)
