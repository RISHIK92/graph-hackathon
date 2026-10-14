"""Whole-pipeline invariants on the seed-1 render (06 §1): I4 shuffled ingestion within each phase,
I3 re-ingestion writes nothing, and a Source interrupted after stage 8 is finished on retry (A58)."""
import uuid

import pytest

from brain import integrity, schema
from brain.config import MAX, ROOT
from brain.db import Graph
from ingest.connectors import read_render
from ingest.pipeline import Ingestor

RENDER = ROOT / "world" / "seeds" / "1" / "render"


def fresh() -> Graph:
    g = Graph(name=f"pipe_{uuid.uuid4().hex[:6]}")
    schema.create(g)
    return g


def state(g: Graph) -> dict:
    tuples = g.ro("MATCH (a:Assertion) WHERE a.retracted_at = $max "
                  "OPTIONAL MATCH (a)-[e:EVIDENCED_BY]->(s:Span) WHERE e.removed_at = $max "
                  "WITH a, collect(DISTINCT s.id) AS ev "
                  "RETURN a.chain_id AS c, a.subject_id AS s, a.object_id AS o, a.object_value AS v, a.negated AS n, "
                  "a.valid_from AS vf, a.valid_to AS vt, a.status AS st, ev", {"max": MAX}, timeout=10000)
    facts = sorted((r["c"], r["s"], r["o"] or "", r["v"] or "", bool(r["n"]), r["vf"], r["vt"], r["st"], tuple(sorted(r["ev"])))
                   for r in tuples)
    sources = sorted(r["id"] for r in g.ro("MATCH (s:Source) WHERE s.kind <> 'world_meta' RETURN s.id AS id", timeout=10000))
    spans = sorted((r["id"], r["ts"]) for r in g.ro("MATCH (s:Span) RETURN s.id AS id, s.ts AS ts", timeout=10000))
    return {"facts": facts, "sources": sources, "spans": spans}


@pytest.fixture(scope="module")
def docs():
    return read_render(RENDER)


@pytest.fixture(scope="module")
def clean(docs):
    g = fresh()
    Ingestor(g).ingest_docs(docs)
    yield g, state(g)
    g.delete()


def test_i4_shuffled_orders_give_identical_state(docs, clean):
    _, base = clean
    assert len(base["facts"]) > 500
    for seed in (7, 23, 99):           # three random orders within each phase (06 §1)
        g = fresh()
        try:
            Ingestor(g).ingest_docs(docs, seed=seed)
            got = state(g)
            assert got["sources"] == base["sources"]
            assert got["spans"] == base["spans"], "span ts must be order-free (minimum over revisions)"
            assert got["facts"] == base["facts"]
        finally:
            g.delete()


def test_i3_reingestion_writes_nothing(docs, clean):
    g, base = clean
    versions = {r["id"]: r["v"] for r in g.ro("MATCH (c:Chain) RETURN c.id AS id, c.version AS v", timeout=10000)}
    counts = g.ro("MATCH (n) WITH count(n) AS nodes MATCH ()-[r]->() RETURN nodes, count(r) AS rels", timeout=10000)[0]
    rep = Ingestor(g).ingest_docs(docs)
    assert rep.sources == 0 and not [r for r in rep.rows if r["outcome"] not in ("dedup_noop",)]
    assert {r["id"]: r["v"] for r in g.ro("MATCH (c:Chain) RETURN c.id AS id, c.version AS v", timeout=10000)} == versions
    assert g.ro("MATCH (n) WITH count(n) AS nodes MATCH ()-[r]->() RETURN nodes, count(r) AS rels", timeout=10000)[0] == counts
    assert state(g) == base


def test_interrupted_source_is_finished_on_retry(docs, clean):
    _, base = clean
    victim = next(d for d in docs if d.kind == "catalog").doc_key
    g = fresh()
    try:
        with pytest.raises(RuntimeError, match="injected failure"):
            Ingestor(g, fail_after_stage8=victim).ingest_docs(docs)
        unfinished = g.ro("MATCH (s:Source {doc_key:$k}) WHERE s.ingested_at = $max RETURN count(s) AS n",
                          {"k": victim, "max": MAX})[0]["n"]
        assert unfinished >= 1, "the interrupted Source must have no completion marker"
        Ingestor(g).ingest_docs(docs)        # retry finishes it, idempotently
        assert state(g) == base
        assert integrity.check(g, deep=True)["ok"]
    finally:
        g.delete()
