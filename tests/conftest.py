import os
import uuid

# Tests are deterministic and offline unless BRAIN_TEST_LLM=1: an empty key disables the provider
# before brain.config loads (its .env loader uses setdefault, so this wins).
if os.environ.get("BRAIN_TEST_LLM") != "1":
    os.environ["OPENROUTER_API_KEY"] = ""

import pytest

from brain import schema, store
from brain.db import Graph

PORTS = {"6.0.1": int(os.environ.get("FALKOR6_PORT", 6391)), "4.22.0": int(os.environ.get("FALKOR4_PORT", 6392))}


def _graph(port: int) -> Graph:
    g = Graph(name=f"test_{uuid.uuid4().hex[:8]}", port=port)
    schema.create(g)
    return g


@pytest.fixture(params=list(PORTS), ids=list(PORTS))
def g(request):
    graph = _graph(PORTS[request.param])
    yield graph
    graph.delete()


@pytest.fixture
def g6():
    graph = _graph(PORTS["6.0.1"])
    yield graph
    graph.delete()


class Clock:
    def __init__(self, t: int = 1000):
        self.t = t

    def __call__(self) -> int:
        return self.t

    def tick(self, n: int = 1) -> int:
        self.t += n
        return self.t


@pytest.fixture
def clock():
    return Clock()


def seed_basic(g: Graph) -> None:
    store.upsert_entities(g, [
        {"id": "team:payments", "name": "Payments", "aliases": []},
        {"id": "team:infra", "name": "Infra", "aliases": ["Infrastructure"]},
        {"id": "team:platform", "name": "Platform", "aliases": []},
        {"id": "system:ledger", "name": "Ledger", "aliases": ["ledger-service"]},
        {"id": "person:priya", "name": "Priya Raman", "aliases": ["Priya"]},
        {"id": "person:bob", "name": "Bob Okafor", "aliases": ["Bob"]},
        {"id": "person:eve", "name": "Eve Lin", "aliases": ["Eve"]},
        {"id": "ticket:rds-42", "name": "RDS-42", "aliases": ["rds42"]},
        {"id": "decision:adr-001", "name": "ADR-001", "aliases": []},
    ])


def make_span(g: Graph, sid: str, text: str, ts: int, src: str = "src:test", kind: str = "wiki",
              role: str = "human") -> None:
    if not store.source_exists(g, src):
        store.create_source(g, {"id": src, "doc_key": src, "kind": kind, "status": "active",
                                "is_latest": True, "ingested_at": 1, "updated_at": ts, "title": src, "uri": ""})
    store.upsert_spans(g, src, [{"id": sid, "doc_key": src, "text": text, "keys": "", "ts": ts,
                                 "author_id": "", "author_role": role, "kind": kind, "embed_model": "none",
                                 "char_start": 0, "char_end": len(text), "ordinal": 0}], latest=True, now=0)
