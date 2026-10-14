"""Chain recomputation as a pure function (02 §3) and the Python past-belief reference (02 §6).

Both the write path and past-belief reads use `walk`. Nothing here touches the graph.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import MAX


@dataclass
class Evidence:
    span_id: str
    form: str
    authority: int
    recorded_at: int
    removed_at: int = MAX
    span_ts: int = 0
    action_id: str = ""
    source_id: str = ""
    replaced_by: str = ""

    def live(self, t: int) -> bool:
        return self.recorded_at <= t < self.removed_at


@dataclass
class Record:
    id: str
    value: str             # object id, "=literal", or "" for non-functional (polarity carries it)
    negated: bool
    valid_from: int
    recorded_at: int
    retracted_at: int = MAX
    evidence: list[Evidence] = field(default_factory=list)

    @property
    def value_id(self) -> str:
        """Sort key and identity of the chain value: object id / literal, then polarity (+ before -)."""
        return f"{self.value}|{'-' if self.negated else '+'}"

    def holds(self, t: int) -> bool:
        return self.recorded_at <= t < self.retracted_at

    def authority_at(self, t: int) -> int:
        live = [e.authority for e in self.evidence if e.live(t) and e.authority >= 1]
        return max(live) if live else 0

    def confirmed_at(self, t: int) -> bool:
        return any(e.live(t) and e.form == "confirmation" for e in self.evidence)


@dataclass
class Run:
    members: list[str]
    value_id: str
    negated: bool
    valid_from: int
    valid_to: int
    authority: int

    @property
    def run_id(self) -> str:
        return self.members[0]


@dataclass
class ChainState:
    status: dict[str, str]                 # assertion id -> current|superseded|disputed|proposed
    valid_to: dict[str, int]
    run_id: dict[str, str]
    authority: dict[str, int]
    supersedes: set[tuple[str, str]]
    continues: set[tuple[str, str]]
    disputes: set[tuple[str, str]]
    runs: list[Run]


def walk(records: list[Record], t: int = MAX - 1) -> ChainState:
    """02 §3 at belief time t. Records not holding at t are ignored entirely."""
    status: dict[str, str] = {}
    authority: dict[str, int] = {}
    valid_to: dict[str, int] = {}
    run_of: dict[str, str] = {}
    sup: set[tuple[str, str]] = set()
    cont: set[tuple[str, str]] = set()
    disp: set[tuple[str, str]] = set()

    active: list[Record] = []
    for r in records:
        if not r.holds(t):
            continue
        a = r.authority_at(t)
        authority[r.id] = a
        if a < 1:                        # step 0: no live evidence of rank >= 1
            status[r.id] = "proposed"
            valid_to[r.id] = MAX
            run_of[r.id] = ""
            continue
        active.append(r)

    # Step 1: valid_from asc, authority desc, confirmed first, value id asc (A30, A52).
    active.sort(key=lambda r: (r.valid_from, -authority[r.id], not r.confirmed_at(t), r.value_id))

    runs: list[Run] = []
    by_id = {r.id: r for r in active}
    for a in active:
        if not runs:
            runs.append(Run([a.id], a.value_id, a.negated, a.valid_from, MAX, authority[a.id]))
            continue
        run = runs[-1]
        last = by_id[run.members[-1]]
        if a.value_id == run.value_id:
            cont.add((a.id, last.id))
            run.members.append(a.id)
            run.authority = max(run.authority, authority[a.id])
        elif a.valid_from == last.valid_from:
            status[a.id] = "disputed"
            disp.add((a.id, last.id))
        elif authority[a.id] >= run.authority:
            run.valid_to = a.valid_from
            sup.add((a.id, last.id))
            runs.append(Run([a.id], a.value_id, a.negated, a.valid_from, MAX, authority[a.id]))
        else:
            status[a.id] = "disputed"
            disp.add((a.id, last.id))

    for i, run in enumerate(runs):
        is_open = i == len(runs) - 1 and run.valid_to == MAX
        for m in run.members:
            status[m] = "current" if is_open else "superseded"
            valid_to[m] = run.valid_to
            run_of[m] = run.run_id
    for a in active:
        if status.get(a.id) == "disputed":
            valid_to[a.id] = MAX
            run_of[a.id] = ""

    return ChainState(status, valid_to, run_of, authority, sup, cont, disp, runs)


# settled disputes (read time, A40/A56)

def dispute_settled(challenger: Record, run: Run, by_id: dict[str, Record], t: int) -> tuple[bool, int | None]:
    """Settled at t when a run member has live confirmation evidence whose time (its span ts)
    is after the authored time of the challenger's latest live rank>=1 evidence."""
    conf_times = [e.span_ts for m in run.members for e in by_id[m].evidence
                  if e.live(t) and e.form == "confirmation"]
    if not conf_times:
        return False, None
    conf_at = max(conf_times)
    ch_ts = [e.span_ts for e in challenger.evidence if e.live(t) and e.authority >= 1]
    last_ev = max(ch_ts) if ch_ts else 0
    return conf_at > last_ev, conf_at


def disputes_against(state: ChainState, run: Run, records: list[Record], t: int) -> list[dict]:
    by_id = {r.id: r for r in records}
    out = []
    for d, target in sorted(state.disputes):
        if target in run.members:
            settled, conf_at = dispute_settled(by_id[d], run, by_id, t)
            out.append({"assertion_id": d, "target": target, "settled": settled, "confirmed_at": conf_at})
    return out


# past belief: the reference engine (02 §6)

def past_belief(records: list[Record], t: int, v: int) -> dict | None:
    """What the brain believed at belief time t about valid time v, for one chain.

    Returns the run whose interval contains v, with members, states at t, disputes against it
    (open or settled at t), and evidence live at t; None when nothing held.
    """
    state = walk(records, t)
    by_id = {r.id: r for r in records}
    for run in state.runs:
        if run.valid_from <= v < run.valid_to:
            return {
                "value": run.value_id.rsplit("|", 1)[0],
                "negated": run.negated,
                "valid_from": run.valid_from,
                "valid_to": run.valid_to,
                "run": sorted(run.members),
                "states": {m: state.status[m] for m in run.members},
                "disputes": disputes_against(state, run, records, t),
                "evidence": {m: sorted(e.span_id for e in by_id[m].evidence
                                       if e.live(t) and e.authority >= 1) for m in run.members},
            }
    return None
