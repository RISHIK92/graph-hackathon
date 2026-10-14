"""Gold from the world declarations only (05 §3.3, A37): never from any chain function.

Chain gold reads the declared `changes[]` in date order: `resolved` moves the value at `at`;
`disputed` keeps the recorded value and lists the challenger. A chain with no change entry has its
single stated fact current from its stated date. No rank logic runs here.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import yaml

from brain import registry
from brain.config import MAX
from brain.db import Graph


@dataclass
class World:
    w: dict
    manifest: dict
    seed_dir: Path

    @classmethod
    def load(cls, seed_dir: Path) -> "World":
        import json
        seed_dir = Path(seed_dir)
        return cls(yaml.safe_load((seed_dir / "world.yaml").read_text()),
                   json.loads((seed_dir / "render" / "manifest.json").read_text()), seed_dir)

    @property
    def today(self) -> int:
        return int(self.manifest.get("today") or self.w["company"].get("today"))

    def names(self) -> dict[str, str]:
        out = {}
        for k in ("people", "teams", "projects", "systems"):
            for e in self.w[k]:
                out[e["id"]] = e["name"]
        for d in self.w["decisions"]:
            out[d["id"]] = d["number"]
        for t in self.w["tickets"]:
            out[t["id"]] = t["key"]
        return out

    def aliases(self, eid: str) -> list[str]:
        for k in ("people", "teams", "projects", "systems"):
            for e in self.w[k]:
                if e["id"] == eid:
                    return list(e.get("aliases") or [])
        return []


def chain_key(pred: str, qual: str, s: str, o: str) -> tuple[str, str, str]:
    p = registry.get(pred, qual)
    if p.key_side == "object":
        return (pred, qual, o)
    if p.key_side == "subject":
        return (pred, qual, s)
    return (pred, qual, f"{s}>{o}")


class ChainGold:
    def __init__(self, world: World):
        self.world = world
        self.facts: dict[tuple, list[dict]] = defaultdict(list)
        for f in world.w["facts"]:
            p = registry.get(f["predicate"], f.get("qualifier") or "")
            key = chain_key(f["predicate"], f.get("qualifier") or "", f["subject"], f.get("object") or "")
            self.facts[key].append(f)
        self.changes: dict[tuple, list[dict]] = defaultdict(list)
        for c in world.w["changes"]:
            p = registry.get(c["predicate"], c.get("qualifier") or "")
            if p.functional:
                key = (c["predicate"], c.get("qualifier") or "", c["key"])
            else:
                key = (c["predicate"], c.get("qualifier") or "", c["key"])
            self.changes[key].append(c)
        for v in self.changes.values():
            v.sort(key=lambda c: c["at"])

    def _value(self, pred: str, f: dict) -> str:
        p = registry.get(pred, f.get("qualifier") or "")
        if not p.functional:
            return "-" if f.get("negated") else "+"
        if p.key_side == "object":
            return f["subject"]
        return f.get("object") or "=" + (f.get("value") or "")

    def state(self, key: tuple, V: int) -> dict | None:
        """{value, since, disputes:[{recorded, challenger, change_id, challenger_correct}], history:[...]}"""
        pred = key[0]
        changes = self.changes.get(key, [])
        facts = sorted(self.facts.get(key, []), key=lambda f: f["valid_from"])
        if not changes:
            cur = [f for f in facts if f["valid_from"] <= V < (f.get("valid_to") or MAX)]
            if not cur:
                return None
            f = cur[-1]
            return {"value": self._value(pred, f), "since": f["valid_from"], "disputes": [], "history": []}
        first = changes[0]
        start = min([f["valid_from"] for f in facts] or [first["at"]])
        value, since, hist, disputes = first["from"], start, [], []
        if since > V:
            return None
        for c in changes:
            if c["at"] > V:
                break
            if c["expected_outcome"] == "resolved":
                hist.append({"value": value, "from": since, "to": c["at"]})
                value, since = c["to"], c["at"]
                disputes = [d for d in disputes if d["recorded"] == value]
            else:
                disputes.append({"recorded": value, "challenger": c["to"], "change_id": c["change_id"],
                                 "challenger_correct": c.get("challenger_correct")})
        disputes = [d for d in disputes if d["recorded"] == value]
        return {"value": value, "since": since, "disputes": disputes, "history": hist}


class SpanGold:
    """Gold spans: spans whose HAS_SPAN interval in a revision overlaps a sentence that states the ref."""

    def __init__(self, world: World, g: Graph):
        self.world, self.g = world, g
        self.by_ref: dict[str, list[dict]] = defaultdict(list)
        for d in world.manifest["documents"]:
            for s in d.get("sentences") or []:
                self.by_ref[s["ref"]].append({"doc": d, **s})
        self._cache: dict[tuple, list[str]] = {}

    def spans(self, ref: str, latest_only: bool = False, states: str | None = None) -> list[str]:
        out: list[str] = []
        for s in self.by_ref.get(ref, []):
            if states and s.get("states") != states:
                continue
            d = s["doc"]
            key = (d["doc_key"], d["updated_at"], s["char_start"], s["char_end"], d.get("path"))
            if key not in self._cache:
                self._cache[key] = self._lookup(d, s)
            out += self._cache[key]
        return sorted(set(out))

    def _lookup(self, d: dict, s: dict) -> list[str]:
        if d["kind"] == "chat":
            rows = self.g.ro("MATCH (src:Source {doc_key:$k})-[h:HAS_SPAN]->(sp:Span) RETURN sp.id AS id",
                             {"k": d["doc_key"]}, template="gold_chat")
            return [r["id"] for r in rows]
        rows = self.g.ro("MATCH (src:Source {doc_key:$k})-[h:HAS_SPAN]->(sp:Span) WHERE src.updated_at = $u "
                         "AND h.char_start < $e AND h.char_end > $s RETURN sp.id AS id",
                         {"k": d["doc_key"], "u": d["updated_at"], "s": s["char_start"], "e": s["char_end"]},
                         template="gold_spans")
        return [r["id"] for r in rows]

    def stale_docs(self) -> set[str]:
        out = set()
        for c in self.world.w["changes"]:
            out |= set(c.get("stale_docs") or [])
        return out
