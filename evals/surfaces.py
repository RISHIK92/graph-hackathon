"""06 §1 "Surface reads": gold for the Overview, side panel, Graph subgraph, source-kind filter and
highlights, from the world declarations only (05 §3.3, A37) via `ChainGold.state`. No chain function runs.

Every function here returns plain sets and dicts so a test (or a CLI run) can diff them against the
API's JSON. `diff()` reports precision and recall with the exact missing and extra members.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from brain.cli import DEFAULT_SEED

from .gold import ChainGold, World

DAY = 86_400_000
DRAWN_TYPES = ("OWNS", "LEADS", "MEMBER_OF", "DEPENDS_ON", "PART_OF")


@dataclass
class Gold:
    world: World
    cg: ChainGold

    @classmethod
    def load(cls, seed_dir: Path | str = DEFAULT_SEED) -> "Gold":
        w = World.load(Path(seed_dir))
        return cls(w, ChainGold(w))

    # sampled valid times (06 §1 Surface reads (3))
    @property
    def today(self) -> int:
        return self.world.today

    @property
    def d_reorg(self) -> int:
        return int(self.world.w["D_reorg"])

    def core_vs(self) -> dict[str, int]:
        d = self.d_reorg
        return {"today": self.today, "D_reorg-1d": d - DAY, "D_reorg": d, "D_reorg+1d": d + DAY}

    def change_vs(self, predicates: tuple[str, ...] = DRAWN_TYPES) -> dict[str, int]:
        """Each declared change's `at` and the day before, for the drawn predicates."""
        out: dict[str, int] = {}
        for c in self.world.w["changes"]:
            if c["predicate"] in predicates:
                out[f"{c['change_id']}@at"] = c["at"]
                out[f"{c['change_id']}@at-1d"] = c["at"] - DAY
        return out

    # entity lists
    def ids(self, kind: str) -> list[str]:
        return [e["id"] for e in self.world.w[kind]]

    def _state(self, key: tuple, V: int) -> dict | None:
        return self.cg.state(key, V)

    def _value(self, key: tuple, V: int) -> str | None:
        st = self._state(key, V)
        return st["value"] if st else None

    # edges valid at V (functional and non-functional)
    def edges(self, V: int) -> set[tuple[str, str, str]]:
        """{(type, source, target)} drawn at V for OWNS, LEADS, primary MEMBER_OF, DEPENDS_ON, PART_OF."""
        out: set[tuple[str, str, str]] = set()
        for x in self.ids("systems") + self.ids("projects"):
            v = self._value(("OWNS", "", x), V)
            if v:
                out.add(("OWNS", v, x))
            if x.startswith("system:"):
                p = self._value(("PART_OF", "", x), V)
                if p:
                    out.add(("PART_OF", x, p))
        for t in self.ids("teams") + self.ids("projects"):
            v = self._value(("LEADS", "", t), V)
            if v:
                out.add(("LEADS", v, t))
        for p in self.ids("people"):
            v = self._value(("MEMBER_OF", "primary", p), V)
            if v:
                out.add(("MEMBER_OF", p, v))
        for key in list(self.cg.facts) + list(self.cg.changes):
            if key[0] == "DEPENDS_ON" and self._value(key, V) == "+":
                s, _, o = key[2].partition(">")
                out.add(("DEPENDS_ON", s, o))
        return out

    def nonprimary_memberships(self, V: int) -> set[tuple[str, str, str]]:
        """Declared non-primary MEMBER_OF edges valid at V. They are not in `edges()` (06 §1 says primary),
        but `/graph` cannot tell them apart (no `primary` flag on its edge rows), so a comparison must add them."""
        out = set()
        for key in list(self.cg.facts) + list(self.cg.changes):
            if key[0] == "MEMBER_OF" and key[1] == "" and self._value(key, V) == "+":
                s, _, o = key[2].partition(">")
                out.add(("MEMBER_OF", s, o))
        return out

    # overview (06 §1 (1))
    def overview(self, V: int) -> dict:
        teams: dict[str, dict] = {}
        for t in self.ids("teams"):
            teams[t] = {"lead": self._value(("LEADS", "", t), V), "members": set(), "owns": set()}
        for p in self.ids("people"):
            v = self._value(("MEMBER_OF", "primary", p), V)
            if v in teams:
                teams[v]["members"].add(p)
        for x in self.ids("systems") + self.ids("projects"):
            v = self._value(("OWNS", "", x), V)
            if v in teams:
                teams[v]["owns"].add(x)
        decisions: dict[str, set[str]] = {}
        for d in self.world.w["decisions"]:
            if self._value(("HAS_STATUS", "", d["id"]), V) == "=accepted":
                aff = set()
                for key in list(self.cg.facts) + list(self.cg.changes):
                    if key[0] == "AFFECTS" and key[2].startswith(d["id"] + ">") and self._value(key, V) == "+":
                        aff.add(key[2].partition(">")[2])
                decisions[d["id"]] = aff
        return {"teams": teams, "decisions": decisions}

    # side panel (06 §1 (2))
    def owner(self, x: str, V: int) -> str | None:
        return self._value(("OWNS", "", x), V)

    def lead(self, t: str, V: int) -> str | None:
        return self._value(("LEADS", "", t), V)

    def depends_on(self, x: str, V: int) -> set[str]:
        return {o for (_, s, o) in self.edges(V) if _ == "DEPENDS_ON" and s == x}

    def depended_on_by(self, x: str, V: int) -> set[str]:
        return {s for (_, s, o) in self.edges(V) if _ == "DEPENDS_ON" and o == x}

    # highlights (06 §1 (5))
    def open_disputes(self, V: int) -> list[dict]:
        """Declared open disputes at V: {predicate, qualifier, key, recorded, challenger, change_id}."""
        out = []
        for key in self.cg.changes:
            st = self._state(key, V)
            for d in (st or {}).get("disputes", []):
                out.append({"predicate": key[0], "qualifier": key[1], "key": key[2], "recorded": d["recorded"],
                            "challenger": d["challenger"], "change_id": d["change_id"]})
        return out

    def dispute_edges(self, V: int) -> set[tuple[str, str]]:
        """Each open dispute's challenger as a (source, target) side edge, entity-valued predicates only."""
        from brain import registry
        out = set()
        for d in self.open_disputes(V):
            p = registry.get(d["predicate"], d["qualifier"])
            if p.literal:
                continue
            if p.key_side == "object":
                out.add((d["challenger"], d["key"]))
            else:
                out.add((d["key"], d["challenger"]))
        return out

    def stale_docs(self) -> set[str]:
        out: set[str] = set()
        for c in self.world.w["changes"]:
            out |= set(c.get("stale_docs") or [])
        return out


# readers of the API's JSON

def api_edges(graph_json: dict, types: tuple[str, ...] = DRAWN_TYPES) -> set[tuple[str, str, str]]:
    return {(e["type"], e["source"], e["target"]) for e in graph_json["edges"] if e["type"] in types}


def api_overview(ov: dict) -> dict:
    teams = {}
    for t in ov["teams"]:
        leads = [x["id"] for x in t["leads"]]
        teams[t["id"]] = {"lead": leads[0] if len(leads) == 1 else (tuple(sorted(leads)) if leads else None),
                          "members": {x["id"] for x in t["members"]}, "owns": {x["id"] for x in t["owns"]}}
    decisions = {d["id"]: {x["id"] for x in d["affects"]} for d in ov["decisions"]}
    return {"teams": teams, "decisions": decisions}


def api_dispute_edges(graph_json: dict) -> set[tuple[str, str]]:
    return {(d["source"], d["target"]) for d in graph_json["disputed"] if d.get("source") and d.get("target")}


# diff

def diff(gold: set, got: set) -> dict:
    missing, extra = gold - got, got - gold
    return {"precision": 1.0 if not got else (len(got & gold) / len(got)),
            "recall": 1.0 if not gold else (len(got & gold) / len(gold)),
            "missing": sorted(missing), "extra": sorted(extra), "ok": not missing and not extra}


def pack_span_ids(pack: dict) -> set[str]:
    """Every span id a pack cites, for the draft-isolation check (06 §1): the caller looks the ids up and
    asserts none has kind `draft` or author_role `agent`. Pack spans don't carry author_role themselves."""
    return {s["span_id"] for it in pack["items"] for s in it["spans"]}
