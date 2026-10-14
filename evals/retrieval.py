"""Retrieval layer (06 §3, §7): variants A, A+R, B, C, D, E over the same questions and the same cached
plan, scored against declared gold. No LLM in the loop.

  A   vector top-k over spans (spans carry their timestamps)
  A+R A plus the same lexical reranker as E
  B   A plus full-text, RRF-fused
  C   B plus entity linking and template tools with NO temporal filter (every run, superseded too, as current)
  D   C plus temporal filtering and supersession (the real tools)
  E   D plus the reranker on text-only items
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from api.agent import Agent, Session
from brain import providers
from brain.db import Graph
from brain.tools import Ctx, chain_view, evidence, run_tool, span_items

VARIANTS = ["A", "A+R", "B", "C", "D", "E"]
_W = re.compile(r"[a-z0-9]+")
STOP = set("who what which why is the a an of to and on in for does do did i should about now today team "
           "currently goes down tell if with be it its this that are was were".split())


@dataclass
class Item:
    label: str
    spans: list[str]
    facts: list[dict]
    current: bool = True
    text: str = ""


def _toks(t: str) -> set[str]:
    return {w for w in _W.findall(t.lower()) if w not in STOP}


def rerank(question: str, items: list[Item]) -> list[Item]:
    q = _toks(question)
    def score(i: int, it: Item) -> float:
        t = _toks(it.text)
        return (len(q & t) / (1 + len(q))) + 1.0 / (10 + i)
    return [it for _, it in sorted(enumerate(items), key=lambda p: -score(*p))]


class Retriever:
    def __init__(self, g: Graph, now: int, as_of: int | None = None):
        self.g, self.now = g, now
        self.as_of = as_of or now
        self.agent = Agent(g)
        self.sess = Session("", "eval", "", anonymous=True)
        self._plans: dict[str, dict] = {}

    def plan(self, q: dict) -> dict:
        if q["id"] not in self._plans:
            self._plans[q["id"]] = self.agent.plan(q["question"], self.sess)
        return self._plans[q["id"]]

    # -- text variants ----------------------------------------------------------------------
    def _span_text(self, ids: list[str]) -> dict[str, dict]:
        rows = self.g.ro("UNWIND $ids AS i MATCH (s:Span {id:i}) RETURN s.id AS id, s.text AS text, s.ts AS ts",
                         {"ids": ids}, template="eval_span_text")
        return {r["id"]: r for r in rows}

    def vector(self, question: str, k: int = 50) -> list[Item]:
        vec = providers.embed([question])[0]
        rows = self.g.ro("CALL db.idx.vector.queryNodes('Span','embedding',$k,vecf32($v)) YIELD node, score "
                         "WHERE node.kind <> 'draft' AND node.author_role <> 'agent' "
                         "RETURN node.id AS id, node.text AS text, node.ts AS ts ORDER BY score ASC",
                         {"k": k, "v": vec}, template="eval_vector")
        return [Item("text_only", [r["id"]], [], True, r["text"]) for r in rows if (r["ts"] or 0) <= self.as_of]

    def hybrid(self, question: str, k: int = 50) -> list[Item]:
        pack = run_tool(Ctx(self.g, now=self.now, as_of=self.as_of), "search_spans", {"query": question, "k": k})
        return [Item("text_only", [s["span_id"] for s in it["spans"]], [], True,
                     " ".join(s["text"] for s in it["spans"])) for it in pack["items"]]

    # -- graph variants ---------------------------------------------------------------------
    def graph_items(self, q: dict, temporal: bool) -> list[Item]:
        plan = self.plan(q)
        ctx = Ctx(self.g, now=self.now, as_of=q.get("as_of") or self.as_of)
        items: list[Item] = []
        for name, args in self.agent.tool_calls(plan, q["question"], ctx, self.sess):
            if name in ("link_entities", "search_spans", "recall_session"):
                continue
            try:
                pack = run_tool(ctx, name, args)
            except Exception:  # noqa: BLE001
                continue
            for it in pack["items"]:
                if not it["facts"] and not it["spans"]:
                    continue
                if temporal:
                    cur = all(f["status"] in ("current", "proposed") for f in it["facts"]) if it["facts"] else True
                    items.append(Item(it["label"], [s["span_id"] for s in it["spans"]], it["facts"], cur,
                                      " ".join(s["text"] for s in it["spans"])))
                else:
                    items += self._all_runs(ctx, it)
        if not temporal:   # dedupe by span set
            seen, out = set(), []
            for i in items:
                key = tuple(i.spans)
                if key not in seen:
                    seen.add(key)
                    out.append(i)
            items = out
        return items

    def _all_runs(self, ctx: Ctx, it: dict) -> list[Item]:
        """Variant C: the same chains, but every run is presented as current, ranked by how much text
        supports it (a graph store with no notion of time)."""
        out = []
        chains = {f.get("assertion_id"): f for f in it["facts"]}
        rows = self.g.ro("UNWIND $ids AS i MATCH (a:Assertion {id:i}) RETURN DISTINCT a.chain_id AS c",
                         {"ids": list(chains)}, template="eval_chains")
        for r in rows:
            v = chain_view(ctx, r["c"])
            for run in v["state"].runs:
                ev = evidence(ctx, run.members)
                sp = span_items(ev)
                facts = [{"subject_id": v["meta"][m].get("s"), "predicate": r["c"].split(":")[0][3:].split("+")[0],
                          "object_id": v["meta"][m].get("o"), "object_value": v["meta"][m].get("ov"),
                          "status": "current"} for m in run.members[:1]]
                out.append(Item("graph", [s["span_id"] for s in sp], facts, True,
                                " ".join(s["text"] for s in sp)))
        out.sort(key=lambda i: -len(i.spans))
        extra = [sp["span_id"] for sp in it["spans"] if not sp.get("cites")]   # e.g. decision rationale spans
        if extra:
            if out:
                out[0].spans += extra
            else:
                out.append(Item(it["label"], extra, [], True, ""))
        return out

    def run(self, variant: str, q: dict) -> list[Item]:
        items = self._run(variant, q)
        if variant in ("C", "D", "E"):
            # graph variants label search hits text_only: they're shown as sources, not as the current
            # fact (06 §3 stale leak counts items labelled current). Text variants present every hit as-is.
            for it in items:
                if not it.facts:
                    it.current = False
        return items

    def _run(self, variant: str, q: dict) -> list[Item]:
        text = q["question"]
        if variant == "A":
            return self.vector(text)[:20]
        if variant == "A+R":
            return rerank(text, self.vector(text))[:20]
        if variant == "B":
            return self.hybrid(text)[:20]
        if variant == "C":
            return (self.graph_items(q, temporal=False) + self.hybrid(text))[:20]
        if variant == "D":
            return (self.graph_items(q, temporal=True) + self.hybrid(text))[:20]
        if variant == "E":
            g = self.graph_items(q, temporal=True)
            return (g + rerank(text, self.hybrid(text)))[:20]
        raise ValueError(variant)


# metrics

def recall_at(items: list[Item], groups: list[list[str]], k: int) -> float | None:
    groups = [set(g) for g in groups if g]
    if not groups:
        return None
    top = {s for it in items[:k] for s in it.spans}
    return sum(1 for g in groups if g & top) / len(groups)


def mrr(items: list[Item], groups: list[list[str]]) -> float | None:
    gold = {s for g in groups for s in g}
    if not gold:
        return None
    for i, it in enumerate(items):
        if gold & set(it.spans):
            return 1.0 / (i + 1)
    return 0.0


def stale_leak(items: list[Item], forbidden: list[str], k: int = 5) -> float | None:
    if not forbidden:
        return None
    f = set(forbidden)
    return 1.0 if any(it.current and f & set(it.spans) for it in items[:k]) else 0.0


def fact_accuracy(items: list[Item], expected: dict | None) -> float | None:
    if not expected:
        return None
    graph = [it for it in items if it.facts]
    if not graph:
        return 0.0
    for f in graph[0].facts:
        if f.get("predicate") == expected.get("predicate") and f.get("subject_id") == expected.get("subject_id") \
                and (f.get("object_id") or "") == (expected.get("object_id") or "") \
                and (f.get("object_value") or "") == (expected.get("object_value") or ""):
            return 1.0
    return 0.0


def dispute_surfacing(items: list[Item], q: dict) -> float | None:
    d = q.get("expected_dispute")
    if not d:
        return None
    for it in items[:10]:
        for f in it.facts:
            if f.get("status") == "current" and f.get("subject_id") == d["recorded"] and f.get("open_disputes"):
                return 1.0
    groups = q["gold_evidence_groups"]
    if len(groups) >= 2 and all(set(g) & {s for it in items[:10] for s in it.spans} for g in groups[:2]):
        return 1.0 if not any(it.facts for it in items[:10]) else 0.0
    return 0.0


def path_coverage(items: list[Item], rel: list[str]) -> float | None:
    if not rel:
        return None
    seen = {f.get("predicate") for it in items[:10] for f in it.facts}
    return sum(1 for r in rel if r in seen) / len(rel)


def score(items: list[Item], q: dict) -> dict:
    return {"recall@5": recall_at(items, q["gold_evidence_groups"], 5),
            "recall@10": recall_at(items, q["gold_evidence_groups"], 10),
            "mrr": mrr(items, q["gold_evidence_groups"]),
            "stale_leak": stale_leak(items, q["forbidden_current_spans"]),
            "fact_accuracy": fact_accuracy(items, q.get("expected_fact")),
            "dispute_surfacing": dispute_surfacing(items, q),
            "path_coverage": path_coverage(items, q.get("expected_relation_types") or [])}
