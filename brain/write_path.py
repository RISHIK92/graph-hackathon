"""The single write path for the fact layer (02).

Every fact write — ingestion, learn_fact, actions — is: read chain(s) → dedup → recompute in Python
(chain.walk) → diff → ONE guarded write query (02 §4) that returns its guard row. Nothing else in the
code base issues writes against Assertions, evidence or projections.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from . import ids, registry
from .chain import Evidence, Record, walk
from .config import MAX
from .db import Graph, GuardFailed, WriteMismatch
from .ids import now_ms

FACT_EDGES = ("SUPERSEDES", "CONTINUES", "DISPUTES")


@dataclass
class Candidate:
    predicate: str
    subject_id: str
    object_id: str = ""
    object_value: str = ""
    qualifier: str = ""
    negated: bool = False
    valid_from: int = 0
    valid_from_basis: str = "source_time"
    span_id: str = ""
    quote_start: int = 0
    quote_end: int = 0
    source_id: str = ""
    form: str = "structured"
    confidence: float = 1.0
    extractor: str = "structured"
    action_id: str = ""          # set when an Action adds this evidence (A62)
    hedged: bool = False
    force_new: bool = False      # drafts and confirmed proposals never deduplicate

    @property
    def authority(self) -> int:
        return registry.FORM_RANK[self.form]

    @property
    def chain_id(self) -> str:
        return registry.chain_id(self.predicate, self.qualifier, self.subject_id, self.object_id)

    @property
    def value(self) -> str:
        p = registry.get(self.predicate, self.qualifier)
        if not p.functional:
            return ""
        if p.key_side == "object":
            return self.subject_id
        return self.object_id or "=" + self.object_value


@dataclass
class ChainSnapshot:
    chain_id: str
    predicate: str
    qualifier: str
    key_id: str
    version: int                      # -1 = chain does not exist yet
    records: list[Record]
    meta: dict[str, dict]             # assertion id -> stored properties
    edges: set[tuple[str, str, str]]  # (type, from, to) with removed_at = MAX
    pairs: set[tuple[str, str]]       # (subject, object) of every assertion, for projection cleanup


@dataclass
class Plan:
    """Everything one guarded write query will do."""
    now: int
    chains: dict[str, ChainSnapshot] = field(default_factory=dict)
    new_assertions: list[dict] = field(default_factory=list)
    new_evidence: list[dict] = field(default_factory=list)
    remove_evidence: list[dict] = field(default_factory=list)   # {aid, span_id, action_id?, source_id?}
    replace_evidence: list[dict] = field(default_factory=list)  # {aid, span_id, replaced_by}
    retract: set[str] = field(default_factory=set)
    updates: list[dict] = field(default_factory=list)
    edges_remove: list[dict] = field(default_factory=list)
    edges_add: list[dict] = field(default_factory=list)
    proj_delete: list[dict] = field(default_factory=list)
    proj_create: list[dict] = field(default_factory=list)
    prop_set: list[dict] = field(default_factory=list)
    # action extras
    new_sources: list[dict] = field(default_factory=list)
    new_spans: list[dict] = field(default_factory=list)
    new_entities: list[dict] = field(default_factory=list)
    action: dict | None = None
    based_on: list[str] = field(default_factory=list)
    elig_on: list[str] = field(default_factory=list)            # must be current with authority >= 2
    produced_assertions: list[str] = field(default_factory=list)
    produced_sources: list[str] = field(default_factory=list)
    targets: list[str] = field(default_factory=list)
    session_id: str = ""
    confirms: list[dict] = field(default_factory=list)          # {from, to}
    motivated_by: list[dict] = field(default_factory=list)      # {decision, span, section, action_id}
    motivated_remove: list[dict] = field(default_factory=list)  # {decision, span, action_id}
    target_status: list[dict] = field(default_factory=list)     # guard: {id, status}
    extra_updates: list[dict] = field(default_factory=list)     # arbitrary node props {label, id, props}
    outcomes: list[dict] = field(default_factory=list)          # per-candidate report

    def touched(self) -> bool:
        return any([self.new_assertions, self.new_evidence, self.remove_evidence, self.replace_evidence,
                    self.updates, self.edges_remove, self.edges_add, self.action, self.new_sources,
                    self.extra_updates, self.motivated_by, self.motivated_remove, self.prop_changes()])

    def prop_changes(self) -> bool:
        return bool(self.prop_set) and any(p.get("changed") for p in self.prop_set)


class Conflict(Exception):
    pass


class ValidationError(Exception):
    pass


# Reading

def load_chain(g: Graph, chain_id: str, predicate: str, qualifier: str, key_id: str) -> ChainSnapshot:
    v = g.ro("MATCH (c:Chain {id:$c}) RETURN c.version AS v", {"c": chain_id}, template="chain_version")
    version = v[0]["v"] if v else -1
    rows = g.ro(
        "MATCH (a:Assertion {chain_id:$c}) "
        "RETURN a.id AS id, a.subject_id AS s, a.object_id AS o, a.object_value AS ov, a.negated AS neg, "
        "a.valid_from AS vf, a.recorded_at AS ra, a.retracted_at AS rt, a.status AS status, "
        "a.valid_to AS vt, a.run_id AS run, a.authority AS auth, a.predicate AS p, a.qualifier AS q, "
        "a.generation AS gen, a.valid_from_basis AS basis",
        {"c": chain_id}, template="chain_assertions")
    ev = g.ro(
        "MATCH (a:Assertion {chain_id:$c})-[e:EVIDENCED_BY]->(s:Span) "
        "RETURN a.id AS aid, s.id AS sid, s.ts AS ts, e.form AS form, e.authority AS auth, "
        "e.recorded_at AS ra, e.removed_at AS rm, e.action_id AS act, e.source_id AS src, "
        "e.replaced_by AS rb",
        {"c": chain_id}, template="chain_evidence")
    edges = g.ro(
        "MATCH (a:Assertion {chain_id:$c})-[r:SUPERSEDES|CONTINUES|DISPUTES]->(b:Assertion) "
        "WHERE r.removed_at = $max RETURN type(r) AS t, a.id AS f, b.id AS to",
        {"c": chain_id, "max": MAX}, template="chain_edges")
    by_a: dict[str, list[Evidence]] = defaultdict(list)
    for e in ev:
        by_a[e["aid"]].append(Evidence(e["sid"], e["form"], e["auth"], e["ra"], e["rm"], e["ts"] or 0,
                                       e["act"] or "", e["src"] or "", e["rb"] or ""))
    records, meta, pairs = [], {}, set()
    p = registry.get(predicate, qualifier)
    for r in rows:
        value = _value_of(p, r["s"], r["o"], r["ov"])
        records.append(Record(r["id"], value, bool(r["neg"]), r["vf"], r["ra"], r["rt"], by_a[r["id"]]))
        meta[r["id"]] = r
        if r["o"]:
            pairs.add((r["s"], r["o"]))
    return ChainSnapshot(chain_id, predicate, qualifier, key_id, version, records, meta,
                         {(e["t"], e["f"], e["to"]) for e in edges}, pairs)


def _value_of(p: registry.Predicate, s: str, o: str, ov: str) -> str:
    if not p.functional:
        return ""
    if p.key_side == "object":
        return s
    return o or "=" + (ov or "")


# Validation (02 §1)

def validate(g: Graph, c: Candidate, entities: dict[str, dict] | None = None, span_text: str | None = None,
             learn_fact_session: str | None = None) -> None:
    p = registry.get(c.predicate, c.qualifier)
    ents = entities or {}
    for eid, allowed in ((c.subject_id, p.subject_labels), (c.object_id, p.object_labels)):
        if not eid:
            continue
        if registry.label_of(eid) not in allowed:
            raise ValidationError(f"{eid} not allowed for {c.predicate}")
    if p.literal:
        if c.object_value not in p.values:
            raise ValidationError(f"value {c.object_value!r} not allowed for {c.predicate}")
    elif not c.object_id:
        raise ValidationError("object_id required")
    if c.form == "confirmation" or c.form == "draft":
        return
    if span_text is None:
        return
    quote = ids.norm(span_text[c.quote_start:c.quote_end]).lower()
    if not quote:
        raise ValidationError("empty quote")
    names = []
    for eid in (c.subject_id, c.object_id):
        if eid and eid in ents:
            group = [n.lower() for n in [ents[eid]["name"], *ents[eid].get("aliases", [])] if n]
            if c.form == "structured":   # system-of-record fields name entities by id
                group.append(eid.lower())
            names.append(group)
    if learn_fact_session is not None:
        if len(names) < 2 or not all(any(n in quote for n in group) for group in names):
            raise ValidationError("learn_fact quote must contain both entity names")
    elif names and not any(any(n in quote for n in group) for group in names):
        raise ValidationError("quote does not name the subject or object")


# Planning: dedup + recompute + diff

class WritePath:
    def __init__(self, g: Graph, clock=now_ms, entity_names: dict[str, str] | None = None):
        self.g = g
        self.clock = clock
        self.entity_names = entity_names or {}

    # -- public API -------------------------------------------------------------------------
    def new_plan(self, now: int | None = None) -> Plan:
        return Plan(now=now if now is not None else self.clock())

    def chain(self, plan: Plan, predicate: str, qualifier: str, subject_id: str, object_id: str) -> ChainSnapshot:
        cid = registry.chain_id(predicate, qualifier, subject_id, object_id)
        if cid not in plan.chains:
            plan.chains[cid] = load_chain(self.g, cid, predicate, qualifier,
                                          registry.key_id(predicate, qualifier, subject_id, object_id))
        return plan.chains[cid]

    def add_candidate(self, plan: Plan, c: Candidate) -> dict:
        """Dedup (02 §2) or stage a new Assertion. Returns {outcome, assertion_id}."""
        snap = self.chain(plan, c.predicate, c.qualifier, c.subject_id, c.object_id)
        value = c.value
        if not c.force_new:
            for r in snap.records:
                if r.retracted_at != MAX or r.id in plan.retract:
                    continue
                if snap.meta.get(r.id, {}).get("status") == "proposed" or _is_proposed(r, plan.now):
                    continue
                if r.value == value and r.negated == c.negated and r.valid_from == c.valid_from:
                    live_same = any(e.span_id == c.span_id and e.live(plan.now) for e in r.evidence)
                    if live_same:
                        out = {"outcome": "dedup_noop", "assertion_id": r.id}
                    else:
                        ev = self._evidence(plan, r.id, c)
                        r.evidence.append(Evidence(c.span_id, c.form, c.authority, plan.now,
                                                   span_ts=ev["span_ts"], action_id=c.action_id,
                                                   source_id=c.source_id))
                        out = {"outcome": "dedup", "assertion_id": r.id}
                    plan.outcomes.append({**out, "candidate": c})
                    return out
        gen = sum(1 for r in snap.records
                  if r.retracted_at != MAX and r.value == value and r.negated == c.negated
                  and r.valid_from == c.valid_from)
        aid = ids.assertion_id(c.predicate, c.subject_id, c.object_id, c.object_value, c.qualifier,
                               c.negated, c.valid_from, gen)
        existing = {r.id for r in snap.records} | {a["id"] for a in plan.new_assertions}
        while aid in existing:  # a proposal with identical inputs to a live fact (practice-repo deviation)
            gen += 1
            aid = ids.assertion_id(c.predicate, c.subject_id, c.object_id, c.object_value, c.qualifier,
                                   c.negated, c.valid_from, gen)
        props = {
            "id": aid, "predicate": c.predicate, "subject_id": c.subject_id, "object_id": c.object_id,
            "object_value": c.object_value, "qualifier": c.qualifier,
            "key_id": snap.key_id, "negated": c.negated, "chain_id": snap.chain_id, "run_id": "",
            "statement": self._statement(c), "valid_from": c.valid_from,
            "valid_from_basis": c.valid_from_basis, "valid_to": MAX, "recorded_at": plan.now,
            "retracted_at": MAX, "status": "proposed", "authority": 0, "generation": gen,
            "confidence": c.confidence, "extractor": c.extractor,
        }
        plan.new_assertions.append(props)
        rec = Record(aid, value, c.negated, c.valid_from, plan.now, MAX, [])
        ev = self._evidence(plan, aid, c)
        rec.evidence.append(Evidence(c.span_id, c.form, c.authority, plan.now, span_ts=ev["span_ts"],
                                     action_id=c.action_id, source_id=c.source_id))
        snap.records.append(rec)
        snap.meta[aid] = {**props, "s": c.subject_id, "o": c.object_id, "ov": c.object_value}
        if c.object_id:
            snap.pairs.add((c.subject_id, c.object_id))
        out = {"outcome": "new", "assertion_id": aid}
        plan.outcomes.append({**out, "candidate": c})
        return out

    def remove_evidence(self, plan: Plan, aid: str, span_id: str = "", action_id: str = "",
                        source_id: str = "", retract_if_empty: bool = True) -> None:
        """Set removed_at on matching live evidence edges (02 §5); retract when nothing live remains."""
        snap = self._snap_for(plan, aid)
        rec = next(r for r in snap.records if r.id == aid)
        for e in rec.evidence:
            if not e.live(plan.now):
                continue
            if span_id and e.span_id != span_id:
                continue
            if action_id and e.action_id != action_id:
                continue
            if source_id and e.source_id != source_id:
                continue
            e.removed_at = plan.now
            plan.remove_evidence.append({"aid": aid, "span_id": e.span_id, "action_id": e.action_id,
                                         "source_id": e.source_id})
        if retract_if_empty and not any(e.live(plan.now) for e in rec.evidence):
            self.retract(plan, aid)

    def mark_replaced(self, plan: Plan, aid: str, span_id: str, replaced_by: str) -> None:
        snap = self._snap_for(plan, aid)
        rec = next(r for r in snap.records if r.id == aid)
        for e in rec.evidence:
            if e.span_id == span_id and e.live(plan.now) and not e.replaced_by:
                e.replaced_by = replaced_by
                plan.replace_evidence.append({"aid": aid, "span_id": span_id, "replaced_by": replaced_by})

    def retract(self, plan: Plan, aid: str) -> None:
        snap = self._snap_for(plan, aid)
        rec = next(r for r in snap.records if r.id == aid)
        if rec.retracted_at == MAX:
            rec.retracted_at = plan.now
            plan.retract.add(aid)

    def load_for_assertion(self, plan: Plan, aid: str) -> ChainSnapshot:
        return self._snap_for(plan, aid)

    # -- recompute + diff -------------------------------------------------------------------
    def finalize(self, plan: Plan) -> None:
        for snap in plan.chains.values():
            self._diff_chain(plan, snap)

    def _diff_chain(self, plan: Plan, snap: ChainSnapshot) -> None:
        now = plan.now
        state = walk(snap.records, now)
        p = registry.get(snap.predicate, snap.qualifier)
        new_ids = {a["id"] for a in plan.new_assertions}
        for r in snap.records:
            m = snap.meta.get(r.id, {})
            if r.retracted_at != MAX:
                target = {"status": "retracted", "valid_to": m.get("vt", MAX) if r.id not in new_ids else MAX,
                          "run_id": "", "authority": r.authority_at(now), "retracted_at": r.retracted_at}
            else:
                target = {"status": state.status[r.id], "valid_to": state.valid_to[r.id],
                          "run_id": state.run_id[r.id], "authority": state.authority[r.id],
                          "retracted_at": MAX}
            current = {"status": m.get("status"), "valid_to": m.get("vt", m.get("valid_to")),
                       "run_id": m.get("run", m.get("run_id")), "authority": m.get("auth", m.get("authority")),
                       "retracted_at": m.get("rt", m.get("retracted_at"))}
            if r.id in new_ids or target != current:
                plan.updates.append({"id": r.id, **target})
        target_edges = ({("SUPERSEDES", a, b) for a, b in state.supersedes}
                        | {("CONTINUES", a, b) for a, b in state.continues}
                        | {("DISPUTES", a, b) for a, b in state.disputes})
        for t, a, b in sorted(snap.edges - target_edges):
            plan.edges_remove.append({"type": t, "from": a, "to": b})
        for t, a, b in sorted(target_edges - snap.edges):
            plan.edges_add.append({"type": t, "from": a, "to": b})

        # projections (02 §3 step 4): a cache, deleted and rebuilt for the whole chain
        if p.projection.startswith("property:"):
            prop = p.projection.split(":", 1)[1]
            cur = next((run for run in state.runs if run.valid_to == MAX and not run.negated), None)
            ent = snap.key_id
            val = cur.value_id.rsplit("|", 1)[0].lstrip("=") if cur else ""
            plan.prop_set.append({"prop": prop, "entity": ent, "value": val,
                                  "aid": cur.run_id if cur else "", "changed": True})
            return
        if not snap.pairs:
            return
        for s, o in sorted(snap.pairs):
            plan.proj_delete.append({"type": p.projection, "from": s, "to": o, "chain": snap.chain_id})
        meta = snap.meta
        for run in state.runs:
            if run.negated:
                continue
            first = meta[run.run_id]
            s, o = first.get("s", first.get("subject_id")), first.get("o", first.get("object_id"))
            plan.proj_create.append({
                "type": p.projection, "from": s, "to": o, "chain": snap.chain_id, "aid": run.run_id,
                "valid_from": run.valid_from, "valid_to": run.valid_to, "authority": run.authority,
                "primary": snap.qualifier == "primary"})

    # -- execute ----------------------------------------------------------------------------
    def execute(self, plan: Plan, retries: int = 0) -> dict:
        """Run the plan as one guarded query. Raises GuardFailed / WriteMismatch."""
        self.finalize(plan)
        if not plan.touched() and not plan.proj_create and not plan.prop_set:
            return {"guard_ok": True, "noop": True, "outcomes": plan.outcomes}
        # I3: an empty diff is a no-op, the chain version stays unchanged.
        if (not plan.new_assertions and not plan.new_evidence and not plan.remove_evidence
                and not plan.replace_evidence and not plan.updates and not plan.edges_add
                and not plan.edges_remove and not plan.action and not plan.new_sources
                and not plan.extra_updates and not plan.motivated_by and not plan.motivated_remove
                and not plan.confirms and not plan.new_entities):
            return {"guard_ok": True, "noop": True, "outcomes": plan.outcomes}
        q, params, expect = build_query(plan)
        res = self.g.write(q, params, template="write_plan")
        if len(res.rows) != 1 or res.rows[0][0] is not True:
            raise WriteMismatch(f"guard row missing: {res.rows}")
        got = res.counters
        if got["nodes_created"] != expect["nodes"] or got["relationships_created"] != expect["rels"]:
            raise WriteMismatch(f"counters {got} != plan {expect}")
        return {"guard_ok": True, "noop": False, "counters": got, "outcomes": plan.outcomes}

    # -- helpers ----------------------------------------------------------------------------
    def _snap_for(self, plan: Plan, aid: str) -> ChainSnapshot:
        for snap in plan.chains.values():
            if any(r.id == aid for r in snap.records):
                return snap
        row = self.g.ro("MATCH (a:Assertion {id:$id}) RETURN a.predicate AS p, a.qualifier AS q, "
                        "a.subject_id AS s, a.object_id AS o", {"id": aid}, template="assertion_chain")
        if not row:
            raise KeyError(aid)
        r = row[0]
        return self.chain(plan, r["p"], r["q"] or "", r["s"], r["o"] or "")

    def _evidence(self, plan: Plan, aid: str, c: Candidate) -> dict:
        ts = self._span_ts(plan, c.span_id)
        plan.new_evidence.append({
            "aid": aid, "span_id": c.span_id, "quote_start": c.quote_start, "quote_end": c.quote_end,
            "recorded_at": plan.now, "removed_at": MAX, "replaced_by": "", "action_id": c.action_id,
            "source_id": c.source_id, "form": c.form, "authority": c.authority})
        return {"span_ts": ts}

    def _span_ts(self, plan: Plan, span_id: str) -> int:
        for s in plan.new_spans:
            if s["id"] == span_id:
                return s["ts"]
        row = self.g.ro("MATCH (s:Span {id:$id}) RETURN s.ts AS ts", {"id": span_id}, template="span_ts")
        return row[0]["ts"] if row else plan.now

    def _statement(self, c: Candidate) -> str:
        n = self.entity_names
        missing = [e for e in (c.subject_id, c.object_id) if e and e not in n]
        if missing:
            for r in self.g.ro("UNWIND $ids AS i MATCH (e:Entity {id:i}) RETURN e.id AS id, e.name AS name",
                               {"ids": missing}, template="entity_names"):
                n[r["id"]] = r["name"]
        return registry.render_statement(c.predicate, c.qualifier, n.get(c.subject_id, c.subject_id),
                                         n.get(c.object_id, c.object_id), c.object_value, c.negated)


def _is_proposed(r: Record, now: int) -> bool:
    return r.authority_at(now) < 1


# Query builder (02 §4 stages; R11 unit CALL per list stage, R13 import first)

_STAGE_N = [0]


def _stage(body: str) -> str:
    """One list stage. 6.0.1 mis-resolves variables once a query has more than ~6 unit CALL {}
    subqueries (practice finding F19), so stages are chained with a grouping-free aggregation
    instead: `WITH count(*)` always yields exactly one row, even when the stage's UNWIND list is
    empty or its MATCH finds nothing, which is what R11 needs."""
    _STAGE_N[0] += 1
    n = _STAGE_N[0]
    # Every stage gets its own variable names: reusing `x`/`p` across aggregation boundaries
    # resolves to the wrong column on 6.0.1 (practice finding F20).
    # And the unwound row is projected before any MATCH: after a `count(*)` boundary, 6.0.1 silently
    # drops rows from `UNWIND … MATCH … MATCH …` (practice finding F21); `WITH x` avoids it.
    body = re.sub(r"^UNWIND (\$\w+) AS x ", r"UNWIND \1 AS x WITH x ", body)
    if not body.startswith("UNWIND"):
        body = "WITH 1 AS one " + body
    body = _VARS.sub(lambda m: f"{m.group(1)}{n}", body)
    return body + f"\nWITH count(*) AS _s{n}\n"


_VARS = re.compile(r"(?<![\w$.`])(x|a|b|c|s|o|p|n|ac|src)(?![\w`])")


def build_query(plan: Plan) -> tuple[str, dict, dict]:
    P: dict[str, Any] = {"now": plan.now, "max": MAX}
    nodes = rels = 0
    P["chains"] = [{"id": s.chain_id, "version": s.version, "predicate": s.predicate,
                    "qualifier": s.qualifier, "key_id": s.key_id} for s in plan.chains.values()]
    nodes += sum(1 for s in plan.chains.values() if s.version == -1)
    P["based_on"] = sorted(set(plan.based_on))
    P["elig_on"] = sorted(set(plan.elig_on))

    # Guard (02 §4 stage 1). Every node it inspects is looked up in ONE leading UNWIND (the sentinel
    # is always in the list, so there is always a row), then every check is a pure list expression:
    # a MATCH placed after an aggregation silently drops rows on 6.0.1 (F21 family).
    lk = [{"k": "g", "id": "sentinel"}] + [{"k": "c", "id": c["id"]} for c in P["chains"]] + \
         [{"k": "a", "id": i} for i in sorted(set(P["based_on"]) | set(P["elig_on"]) |
                                              {t["id"] for t in plan.target_status})]
    P["lk"] = lk
    P["tstat"] = [{"id": t["id"], "status": t["status"]} for t in plan.target_status]
    q = ["UNWIND $lk AS l\nWITH l\n"
         "OPTIONAL MATCH (c:Chain {id: l.id}) WHERE l.k = 'c'\n"
         "WITH l, c\n"
         "OPTIONAL MATCH (a:Assertion {id: l.id}) WHERE l.k = 'a'\n"
         "WITH collect(CASE WHEN c IS NULL THEN null ELSE {id: c.id, version: c.version} END) AS cs, "
         "collect(CASE WHEN a IS NULL THEN null ELSE {id: a.id, status: a.status, authority: a.authority, "
         "retracted_at: a.retracted_at} END) AS got\n"
         "WITH all(x IN $chains WHERE coalesce(head([y IN cs WHERE y.id = x.id | y.version]), -1) = x.version) "
         "AND all(i IN $based_on WHERE any(y IN got WHERE y.id = i AND y.status = 'current' AND y.retracted_at > $now)) "
         "AND all(i IN $elig_on WHERE any(y IN got WHERE y.id = i AND y.status = 'current' AND y.retracted_at > $now "
         "AND y.authority >= 2)) "
         "AND all(x IN $tstat WHERE any(y IN got WHERE y.id = x.id AND y.status = x.status)) AS ok\n"
         "FOREACH (_ IN CASE WHEN ok THEN [] ELSE [1] END | CREATE (:GuardFail {id:'sentinel'}))\n"
         "WITH count(*) AS _g\n"]

    # Deletes run first: on 6.0.1 a DELETE stage placed after a SET stage fails with
    # "Variable p not found" (practice finding F20).
    for t in sorted({p["type"] for p in plan.proj_delete}):
        P[f"pd_{t}"] = [p for p in plan.proj_delete if p["type"] == t]
        q.append(_stage(f"UNWIND $pd_{t} AS x MATCH (s:Entity {{id:x.from}})-[p:{t}]->(o:Entity {{id:x.to}}) "
                        "WHERE p.chain = x.chain DELETE p"))
    q.append(_stage("UNWIND $chains AS x MERGE (c:Chain {id:x.id}) ON CREATE SET c.predicate = x.predicate, "
                    "c.qualifier = x.qualifier, c.key_id = x.key_id, c.version = 0"))

    if plan.new_entities:
        P["new_entities"] = plan.new_entities
        nodes += len(plan.new_entities)
        labels = sorted({e["label"] for e in plan.new_entities})
        for lab in labels:
            key = f"ne_{lab}"
            P[key] = [e["props"] for e in plan.new_entities if e["label"] == lab]
            q.append(_stage(f"UNWIND ${key} AS x CREATE (n:Entity:{lab}) SET n += x"))

    if plan.new_sources:
        P["new_sources"] = plan.new_sources
        nodes += len(plan.new_sources)
        q.append(_stage("UNWIND $new_sources AS x CREATE (s:Source) SET s += x"))
    if plan.new_spans:
        P["new_spans"] = [{k: v for k, v in s.items() if k not in ("source_id", "char_start", "char_end", "ordinal")}
                          for s in plan.new_spans]
        P["span_links"] = [{"id": s["id"], "source_id": s["source_id"], "char_start": s["char_start"],
                            "char_end": s["char_end"], "ordinal": s.get("ordinal", 0)} for s in plan.new_spans]
        nodes += len(plan.new_spans)
        rels += len(plan.new_spans)
        q.append(_stage("UNWIND $new_spans AS x CREATE (s:Span) SET s += x"))
        q.append(_stage("UNWIND $span_links AS x MATCH (src:Source {id:x.source_id}) MATCH (s:Span {id:x.id}) "
                        "CREATE (src)-[:HAS_SPAN {char_start:x.char_start, char_end:x.char_end, ordinal:x.ordinal, "
                        "heading_path:'', recorded_at:$now, removed_at:$max}]->(s)"))

    if plan.new_assertions:
        P["new_assertions"] = plan.new_assertions
        nodes += len(plan.new_assertions)
        with_obj = [a for a in plan.new_assertions if a["object_id"]]
        rels += 2 * len(plan.new_assertions) + len(with_obj)
        q.append(_stage("UNWIND $new_assertions AS x CREATE (a:Assertion) SET a += x"))
        q.append(_stage("UNWIND $new_assertions AS x MATCH (a:Assertion {id:x.id}) MATCH (c:Chain {id:x.chain_id}) "
                        "CREATE (a)-[:OF_CHAIN]->(c)"))
        q.append(_stage("UNWIND $new_assertions AS x MATCH (a:Assertion {id:x.id}) MATCH (s:Entity {id:x.subject_id}) "
                        "CREATE (a)-[:SUBJECT]->(s)"))
        P["with_obj"] = [{"id": a["id"], "object_id": a["object_id"]} for a in with_obj]
        q.append(_stage("UNWIND $with_obj AS x MATCH (a:Assertion {id:x.id}) MATCH (o:Entity {id:x.object_id}) "
                        "CREATE (a)-[:OBJECT]->(o)"))

    if plan.new_evidence:
        P["new_evidence"] = plan.new_evidence
        rels += len(plan.new_evidence)
        q.append(_stage("UNWIND $new_evidence AS x MATCH (a:Assertion {id:x.aid}) MATCH (s:Span {id:x.span_id}) "
                        "CREATE (a)-[:EVIDENCED_BY {quote_start:x.quote_start, quote_end:x.quote_end, "
                        "recorded_at:x.recorded_at, removed_at:x.removed_at, replaced_by:x.replaced_by, "
                        "action_id:x.action_id, source_id:x.source_id, form:x.form, authority:x.authority}]->(s)"))
    if plan.remove_evidence:
        P["remove_evidence"] = plan.remove_evidence
        q.append(_stage("UNWIND $remove_evidence AS x MATCH (a:Assertion {id:x.aid})-[e:EVIDENCED_BY]->(s:Span {id:x.span_id}) "
                        "WHERE e.removed_at = $max AND e.action_id = x.action_id AND e.source_id = x.source_id "
                        "SET e.removed_at = $now"))
    if plan.replace_evidence:
        P["replace_evidence"] = plan.replace_evidence
        q.append(_stage("UNWIND $replace_evidence AS x MATCH (a:Assertion {id:x.aid})-[e:EVIDENCED_BY]->(s:Span {id:x.span_id}) "
                        "WHERE e.removed_at = $max SET e.replaced_by = x.replaced_by"))

    if plan.updates:
        P["updates"] = plan.updates
        q.append(_stage("UNWIND $updates AS x MATCH (a:Assertion {id:x.id}) SET a.status = x.status, "
                        "a.valid_to = x.valid_to, a.run_id = x.run_id, a.authority = x.authority, "
                        "a.retracted_at = x.retracted_at"))

    for t in FACT_EDGES:
        rm = [e for e in plan.edges_remove if e["type"] == t]
        ad = [e for e in plan.edges_add if e["type"] == t]
        if rm:
            P[f"rm_{t}"] = rm
            q.append(_stage(f"UNWIND $rm_{t} AS x MATCH (a:Assertion {{id:x.from}})-[r:{t}]->(b:Assertion {{id:x.to}}) "
                            "WHERE r.removed_at = $max SET r.removed_at = $now"))
        if ad:
            P[f"ad_{t}"] = ad
            rels += len(ad)
            q.append(_stage(f"UNWIND $ad_{t} AS x MATCH (a:Assertion {{id:x.from}}) MATCH (b:Assertion {{id:x.to}}) "
                            f"CREATE (a)-[:{t} {{recorded_at:$now, removed_at:$max}}]->(b)"))

    for t in sorted({p["type"] for p in plan.proj_create}):
        cr = [p for p in plan.proj_create if p["type"] == t]
        P[f"pc_{t}"] = cr
        rels += len(cr)
        q.append(_stage(f"UNWIND $pc_{t} AS x MATCH (s:Entity {{id:x.from}}) MATCH (o:Entity {{id:x.to}}) "
                        f"CREATE (s)-[:{t} {{aid:x.aid, valid_from:x.valid_from, valid_to:x.valid_to, "
                        "authority:x.authority, chain:x.chain, primary:x.primary}]->(o)"))
    for prop in sorted({p["prop"] for p in plan.prop_set}):
        P[f"ps_{prop}"] = [p for p in plan.prop_set if p["prop"] == prop]
        q.append(_stage(f"UNWIND $ps_{prop} AS x MATCH (n:Entity {{id:x.entity}}) "
                        f"SET n.{prop} = x.value, n.{prop}_aid = x.aid"))

    for i, u in enumerate(plan.extra_updates):
        P[f"xu_{i}"] = u["props"]
        P[f"xid_{i}"] = u["id"]
        q.append(_stage(f"MATCH (n:{u['label']} {{id:$xid_{i}}}) SET n += $xu_{i}"))

    if plan.confirms:
        P["confirms"] = plan.confirms
        rels += len(plan.confirms)
        q.append(_stage("UNWIND $confirms AS x MATCH (a:Assertion {id:x.from}) MATCH (b:Assertion {id:x.to}) "
                        "CREATE (a)-[:CONFIRMS {recorded_at:$now}]->(b)"))
    if plan.motivated_by:
        P["motivated_by"] = plan.motivated_by
        rels += len(plan.motivated_by)
        q.append(_stage("UNWIND $motivated_by AS x MATCH (d:Decision {id:x.decision}) MATCH (s:Span {id:x.span}) "
                        "CREATE (d)-[:MOTIVATED_BY {section:x.section, action_id:x.action_id, "
                        "recorded_at:$now, removed_at:$max}]->(s)"))
    if plan.motivated_remove:
        P["motivated_remove"] = plan.motivated_remove
        q.append(_stage("UNWIND $motivated_remove AS x MATCH (d:Decision {id:x.decision})-[m:MOTIVATED_BY]->(s:Span) "
                        "WHERE m.action_id = x.action_id AND m.removed_at = $max SET m.removed_at = $now"))

    if plan.action:
        P["action"] = plan.action
        nodes += 1
        q.append(_stage("CREATE (ac:Action) SET ac += $action"))
        for key, lst, label, rel in (("ab", plan.based_on, "Assertion", "BASED_ON"),
                                     ("ap", plan.produced_assertions, "Assertion", "PRODUCED"),
                                     ("as", plan.produced_sources, "Source", "PRODUCED"),
                                     ("at", plan.targets, "Entity", "TARGETS")):
            vals = sorted(set(lst))
            if not vals:
                continue
            P[key] = vals
            rels += len(vals)
            extra = " {belief_ts:$now}" if rel == "BASED_ON" else ""
            q.append(_stage(f"UNWIND ${key} AS x MATCH (ac:Action {{id:$action.id}}) MATCH (n:{label} {{id:x}}) "
                            f"CREATE (ac)-[:{rel}{extra}]->(n)"))
        if plan.session_id:
            P["sess"] = plan.session_id
            rels += 1
            q.append(_stage("MATCH (ac:Action {id:$action.id}) MATCH (s:Source {id:$sess}) "
                            "CREATE (ac)-[:IN_SESSION]->(s)"))

    q.append(_stage("UNWIND $chains AS x MATCH (c:Chain {id:x.id}) SET c.version = c.version + 1"))
    q.append("RETURN true AS guard_ok")
    return "".join(q), P, {"nodes": nodes, "rels": rels}


def payload(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, default=str)


__all__ = ["Candidate", "WritePath", "Plan", "GuardFailed", "WriteMismatch", "Conflict", "ValidationError",
           "load_chain", "validate", "build_query", "now_ms", "payload"]
