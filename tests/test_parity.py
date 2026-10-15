"""I9 full parity (02 §6, 08 §3, README A38/A53): the Python reference and the Cypher past-belief
engine return the same complete result on real graphs built through the write path, and each equals
the hand-written expected row. Expected results below are transcribed from 08 §3 and its source
fixtures, never from either engine (A63).

Conventions (08): A < B by value id, so A = team:infra (lead Bob) and B = team:payments (lead Priya);
P = team:payments, I = team:infra on the Ledger chain. Recording times are the clock; span `ts` equals
the recording time unless a fixture states otherwise (A56).
"""
from __future__ import annotations

import itertools

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from brain import chain as chainmod
from brain import registry, store
from brain.actions import Actions, Actor, Refused
from brain.config import MAX
from brain.past_belief_cypher import past_belief_cypher
from brain.write_path import Candidate, WritePath, load_chain

from .conftest import Clock, make_span, seed_basic

A, B = "team:infra", "team:payments"          # A < B
P, I = "team:payments", "team:infra"          # I < P
LEDGER = "system:ledger"
OWNS = registry.chain_id("OWNS", "", "", LEDGER)


# helpers

def _fact(wp, pred, s, o, vf, span, form="structured", value="", neg=False):
    plan = wp.new_plan()
    out = wp.add_candidate(plan, Candidate(pred, s, o, object_value=value, valid_from=vf, span_id=span,
                                           quote_end=5, form=form, source_id="src:test", negated=neg))
    wp.execute(plan)
    return out["assertion_id"]


def _retract(wp, aid, span_id="", source_id=""):
    plan = wp.new_plan()
    wp.load_for_assertion(plan, aid)
    wp.remove_evidence(plan, aid, span_id=span_id, source_id=source_id)
    wp.execute(plan)


def py(g, cid, t, v):
    pred_q, _, _ = cid[3:].partition(":")
    pred, _, qual = pred_q.partition("+")
    return chainmod.past_belief(load_chain(g, cid, pred, qual, "").records, t, v)


def both(g, cid, t, v):
    """Both engines, asserting I9 parity, returning the (shared) result."""
    a = py(g, cid, t, v)
    b = past_belief_cypher(g, cid, t, v)
    assert a == b, f"engines differ at T={t} V={v}:\n python={a}\n cypher={b}"
    return a


def expect(value, negated, vf, vt, members, states, disputes, evidence):
    return {"value": value, "negated": negated, "valid_from": vf, "valid_to": vt, "run": sorted(members),
            "states": states, "disputes": disputes, "evidence": evidence}


def conf_span(g, res):
    """The confirmation span written by confirm_fact (one Span per confirmation Source, 02 §8)."""
    rows = g.ro("MATCH (:Source {id:$s})-[:HAS_SPAN]->(sp:Span) RETURN sp.id AS id", {"s": res["confirmation_source"]})
    assert len(rows) == 1
    return rows[0]["id"]


def actor(pid):
    return Actor(pid, client="test")


@pytest.fixture
def world(g):
    """Leads at rank 4 so confirmers are eligible (08: every confirmer is eligible)."""
    seed_basic(g)
    store.upsert_entities(g, [{"id": "system:aurora", "name": "Aurora", "aliases": []}])
    clock = Clock(100)
    for i in range(40):
        make_span(g, f"sp{i}", f"span {i}", 1)
    wp = WritePath(g, clock)
    _fact(wp, "LEADS", "person:priya", "team:payments", 1, "sp0")
    _fact(wp, "LEADS", "person:bob", "team:infra", 1, "sp1")
    return {"g": g, "clock": clock, "wp": wp, "acts": Actions(g, clock)}


def span(g, sid, ts):
    make_span(g, sid, f"text {sid}", ts)


# FX-PB-1: predicate representation

def test_fx_pb1_owns_entity_chain_fx_r1_s3(world):
    """FX-R1-S3: A from v10 (rank 4), true challenger B from v20 (rank 1), A's lead confirms B at C30, undo U40."""
    g, clock, wp, acts = world["g"], world["clock"], world["wp"], world["acts"]
    clock.t = 1; span(g, "sa", 1); a = _fact(wp, "OWNS", A, LEDGER, 10, "sa")
    clock.t = 2; span(g, "sb", 2); b = _fact(wp, "OWNS", B, LEDGER, 20, "sb", form="chat")
    clock.t = 30; res = acts.confirm_fact(actor("person:bob"), assertion_id=b)
    cs = conf_span(g, res)
    clock.t = 40; acts.undo_action(actor("person:bob"), res["action_id"])
    # T25 / V25: A, with B open
    assert both(g, OWNS, 25, 25) == expect(A, False, 10, MAX, [a], {a: "current"},
                                           [{"assertion_id": b, "target": a, "settled": False, "confirmed_at": None}],
                                           {a: ["sa"]})
    # After C30: B current from v20 (rank 4, confirmed); A superseded [v10, v20); no dispute
    assert both(g, OWNS, 35, 25) == expect(B, False, 20, MAX, [b], {b: "current"}, [], {b: sorted(["sb", cs])})
    assert both(g, OWNS, 35, 15) == expect(A, False, 10, 20, [a], {a: "superseded"}, [], {a: ["sa"]})
    # After U40: as before C30 (I8); the confirmation evidence is no longer visible
    assert both(g, OWNS, 45, 25) == expect(A, False, 10, MAX, [a], {a: "current"},
                                           [{"assertion_id": b, "target": a, "settled": False, "confirmed_at": None}],
                                           {a: ["sa"]})
    assert both(g, OWNS, 45, 5) is None


def test_fx_pb1_has_status_literal_chain(world):
    """FX-R1-S9's HAS_STATUS rows: accepted from v10, superseded from v30; literal chains match no OBJECT."""
    g, clock, wp = world["g"], world["clock"], world["wp"]
    cid = registry.chain_id("HAS_STATUS", "", "decision:adr-001", "")
    clock.t = 1; acc = _fact(wp, "HAS_STATUS", "decision:adr-001", "", 10, "sp2", value="accepted")
    clock.t = 2; sup = _fact(wp, "HAS_STATUS", "decision:adr-001", "", 30, "sp3", value="superseded")
    assert both(g, cid, 5, 20) == expect("=accepted", False, 10, 30, [acc], {acc: "superseded"}, [], {acc: ["sp2"]})
    assert both(g, cid, 5, 35) == expect("=superseded", False, 30, MAX, [sup], {sup: "current"}, [], {sup: ["sp3"]})
    assert both(g, cid, 1, 35) == expect("=accepted", False, 10, MAX, [acc], {acc: "current"}, [], {acc: ["sp2"]})


def test_fx_pb1_has_state_literal_chain(world):
    """HAS_STATE open from v10, done from v20, read at V15 and V25 (08 §3 FX-PB-1; 'closed' is `done` here)."""
    g, clock, wp = world["g"], world["clock"], world["wp"]
    cid = registry.chain_id("HAS_STATE", "", "ticket:rds-42", "")
    clock.t = 1; o = _fact(wp, "HAS_STATE", "ticket:rds-42", "", 10, "sp4", value="open")
    clock.t = 2; d = _fact(wp, "HAS_STATE", "ticket:rds-42", "", 20, "sp5", value="done")
    assert both(g, cid, 9, 15) == expect("=open", False, 10, 20, [o], {o: "superseded"}, [], {o: ["sp4"]})
    assert both(g, cid, 9, 25) == expect("=done", False, 20, MAX, [d], {d: "current"}, [], {d: ["sp5"]})


def test_fx_pb1_depends_on_positive_negative_chain(world):
    """FX-R1-S14: one span, `+` from v10 and `-` from v20; V15 'held', V25 'did not hold'."""
    g, clock, wp = world["g"], world["clock"], world["wp"]
    cid = registry.chain_id("DEPENDS_ON", "", LEDGER, "system:aurora")
    clock.t = 1
    plan = wp.new_plan()
    plus = wp.add_candidate(plan, Candidate("DEPENDS_ON", LEDGER, "system:aurora", valid_from=10, span_id="sp6",
                                            quote_end=5, form="prose", source_id="src:test"))["assertion_id"]
    minus = wp.add_candidate(plan, Candidate("DEPENDS_ON", LEDGER, "system:aurora", valid_from=20, span_id="sp6",
                                             quote_end=5, form="prose", source_id="src:test", negated=True))["assertion_id"]
    wp.execute(plan)
    assert plus != minus
    assert both(g, cid, 5, 15) == expect("", False, 10, 20, [plus], {plus: "superseded"}, [], {plus: ["sp6"]})
    assert both(g, cid, 5, 25) == expect("", True, 20, MAX, [minus], {minus: "current"}, [], {minus: ["sp6"]})


# FX-PB-3: run reconstruction (FX-R1-S11)

def test_fx_pb3_run_rebuilt_at_t_fx_r1_s11(world):
    """A1 v10 rank 4; B v15 rank 1; A1 confirmed at C20; A2 (same value) v25 rank 4 at r30.
    T35 / V30: run {A1, A2}, [v10, inf), B settled (confirmation on member A1)."""
    g, clock, wp, acts = world["g"], world["clock"], world["wp"], world["acts"]
    clock.t = 1; span(g, "x", 1); a1 = _fact(wp, "OWNS", A, LEDGER, 10, "x")
    clock.t = 2; span(g, "y", 2); b = _fact(wp, "OWNS", B, LEDGER, 15, "y", form="chat")
    clock.t = 20; res = acts.confirm_fact(actor("person:bob"), assertion_id=a1)
    cs = conf_span(g, res)
    clock.t = 30; span(g, "z", 30); a2 = _fact(wp, "OWNS", A, LEDGER, 25, "z")
    assert both(g, OWNS, 35, 30) == expect(A, False, 10, MAX, [a1, a2], {a1: "current", a2: "current"},
                                           [{"assertion_id": b, "target": a1, "settled": True, "confirmed_at": 20}],
                                           {a1: sorted(["x", cs]), a2: ["z"]})
    # before A2 was recorded the run is {A1} alone, still settled
    assert both(g, OWNS, 25, 30) == expect(A, False, 10, MAX, [a1], {a1: "current"},
                                           [{"assertion_id": b, "target": a1, "settled": True, "confirmed_at": 20}],
                                           {a1: sorted(["x", cs])})


# FX-PB-4: timeline changes

def test_fx_pb4_superseder_retraction(world):
    """A from v10 (rank 2); B from v20 (rank 2) at r20; B retracted at r30. T25/V25: B. T35/V25: A, [v10, inf)."""
    g, clock, wp = world["g"], world["clock"], world["wp"]
    clock.t = 10; span(g, "sa", 10); a = _fact(wp, "OWNS", A, LEDGER, 10, "sa", form="prose")
    clock.t = 20; span(g, "sb", 20); b = _fact(wp, "OWNS", B, LEDGER, 20, "sb", form="prose")
    clock.t = 30; _retract(wp, b, span_id="sb")
    assert both(g, OWNS, 25, 25) == expect(B, False, 20, MAX, [b], {b: "current"}, [], {b: ["sb"]})
    assert both(g, OWNS, 25, 15) == expect(A, False, 10, 20, [a], {a: "superseded"}, [], {a: ["sa"]})
    assert both(g, OWNS, 35, 25) == expect(A, False, 10, MAX, [a], {a: "current"}, [], {a: ["sa"]})
    assert both(g, OWNS, 15, 25) == expect(A, False, 10, MAX, [a], {a: "current"}, [], {a: ["sa"]})


# FX-PB-5: disputes

def test_fx_pb5_wrong_challenger_fx_r1_s4(world):
    """B is wrong: confirm A (current, open dispute) at C30, undo at U40. After C30 B is settled; after U40 open."""
    g, clock, wp, acts = world["g"], world["clock"], world["wp"], world["acts"]
    clock.t = 1; span(g, "sa", 1); a = _fact(wp, "OWNS", A, LEDGER, 10, "sa")
    clock.t = 2; span(g, "sb", 2); b = _fact(wp, "OWNS", B, LEDGER, 20, "sb", form="chat")
    clock.t = 30; res = acts.confirm_fact(actor("person:bob"), assertion_id=a)
    cs = conf_span(g, res)
    clock.t = 40; acts.undo_action(actor("person:bob"), res["action_id"])
    assert both(g, OWNS, 35, 35) == expect(A, False, 10, MAX, [a], {a: "current"},
                                           [{"assertion_id": b, "target": a, "settled": True, "confirmed_at": 30}],
                                           {a: sorted(["sa", cs])})
    assert both(g, OWNS, 45, 35) == expect(A, False, 10, MAX, [a], {a: "current"},
                                           [{"assertion_id": b, "target": a, "settled": False, "confirmed_at": None}],
                                           {a: ["sa"]})


def test_fx_pb5_equal_date_lower_rank_tie_confirmed_then_undone(world):
    """A v10 rank 4, B v10 rank 1 (equal_date_dispute). Confirm B at C20 (confirmed wins the tie, A30);
    A is disputed and settled (A40). Undo at U30: A current again, B open."""
    g, clock, wp, acts = world["g"], world["clock"], world["wp"], world["acts"]
    clock.t = 1; span(g, "sa", 1); a = _fact(wp, "OWNS", A, LEDGER, 10, "sa")
    clock.t = 2; span(g, "sb", 2); b = _fact(wp, "OWNS", B, LEDGER, 10, "sb", form="chat")
    assert both(g, OWNS, 5, 10) == expect(A, False, 10, MAX, [a], {a: "current"},
                                          [{"assertion_id": b, "target": a, "settled": False, "confirmed_at": None}],
                                          {a: ["sa"]})
    clock.t = 20; res = acts.confirm_fact(actor("person:bob"), assertion_id=b)
    cs = conf_span(g, res)
    assert both(g, OWNS, 25, 10) == expect(B, False, 10, MAX, [b], {b: "current"},
                                           [{"assertion_id": a, "target": b, "settled": True, "confirmed_at": 20}],
                                           {b: sorted(["sb", cs])})
    clock.t = 30; acts.undo_action(actor("person:bob"), res["action_id"])
    assert both(g, OWNS, 35, 10) == expect(A, False, 10, MAX, [a], {a: "current"},
                                           [{"assertion_id": b, "target": a, "settled": False, "confirmed_at": None}],
                                           {a: ["sa"]})


def test_fx_pb5_reopened_while_confirmation_live_fx_r1_s15(world):
    """A (rank 4) and B (rank 1) both v10. Confirm B at C20. New A evidence authored r30 reopens A.
    C40 (confirm A) is refused; the state keeps one confirmation: B current, A disputed and open."""
    g, clock, wp, acts = world["g"], world["clock"], world["wp"], world["acts"]
    clock.t = 1; span(g, "sa", 1); a = _fact(wp, "OWNS", A, LEDGER, 10, "sa")
    clock.t = 2; span(g, "sb", 2); b = _fact(wp, "OWNS", B, LEDGER, 10, "sb", form="chat")
    clock.t = 20; res = acts.confirm_fact(actor("person:bob"), assertion_id=b)
    cs = conf_span(g, res)
    clock.t = 30; span(g, "sa2", 30); assert _fact(wp, "OWNS", A, LEDGER, 10, "sa2") == a   # dedup (02 §2)
    assert both(g, OWNS, 25, 10) == expect(B, False, 10, MAX, [b], {b: "current"},
                                           [{"assertion_id": a, "target": b, "settled": True, "confirmed_at": 20}],
                                           {b: sorted(["sb", cs])})
    clock.t = 40
    with pytest.raises(Refused, match="undo that confirmation first"):
        acts.confirm_fact(actor("person:priya"), assertion_id=a)
    assert both(g, OWNS, 45, 10) == expect(B, False, 10, MAX, [b], {b: "current"},
                                           [{"assertion_id": a, "target": b, "settled": False, "confirmed_at": 20}],
                                           {b: sorted(["sb", cs])})


# Review 2 items

def test_fx_pb_e1_settledness_scope(world):
    """P@t2 (rank 4), confirmed at C3 against chat I@t3 (rank 1, authored before C3). Roster P@t4 (rank 4)
    continues the run. Read after all events at V5: run {P@t2, P@t4}, [t2, inf), I settled."""
    g, clock, wp, acts = world["g"], world["clock"], world["wp"], world["acts"]
    clock.t = 1; span(g, "r1", 1); p2 = _fact(wp, "OWNS", P, LEDGER, 2, "r1")
    clock.t = 2; span(g, "ch", 2); i3 = _fact(wp, "OWNS", I, LEDGER, 3, "ch", form="chat")
    clock.t = 3; res = acts.confirm_fact(actor("person:priya"), assertion_id=p2)
    cs = conf_span(g, res)
    clock.t = 4; span(g, "r2", 4); p4 = _fact(wp, "OWNS", P, LEDGER, 4, "r2")
    assert both(g, OWNS, 100, 5) == expect(P, False, 2, MAX, [p2, p4], {p2: "current", p4: "current"},
                                           [{"assertion_id": i3, "target": p2, "settled": True, "confirmed_at": 3}],
                                           {p2: sorted(["r1", cs]), p4: ["r2"]})


def test_fx_pb_e2_run_id_is_current_only(world):
    """P@t4 recorded at T1 = 1; same-value P@t2 inserted at T2 = 3. Read at T = 2: run {P@t4}, [t4, inf).
    Read at T > T2: run {P@t2, P@t4}, [t2, inf). The stored run_id (now P@t2) is not used."""
    g, clock, wp = world["g"], world["clock"], world["wp"]
    clock.t = 1; span(g, "a", 1); p4 = _fact(wp, "OWNS", P, LEDGER, 4, "a")
    clock.t = 3; span(g, "b", 3); p2 = _fact(wp, "OWNS", P, LEDGER, 2, "b")
    stored = {r["id"]: r["run"] for r in g.ro("MATCH (a:Assertion {chain_id:$c}) RETURN a.id AS id, a.run_id AS run",
                                              {"c": OWNS})}
    assert stored == {p4: p2, p2: p2}
    assert both(g, OWNS, 2, 5) == expect(P, False, 4, MAX, [p4], {p4: "current"}, [], {p4: ["a"]})
    assert both(g, OWNS, 2, 3) is None
    assert both(g, OWNS, 10, 5) == expect(P, False, 2, MAX, [p2, p4], {p2: "current", p4: "current"}, [],
                                          {p2: ["b"], p4: ["a"]})
    assert both(g, OWNS, 10, 3) == expect(P, False, 2, MAX, [p2, p4], {p2: "current", p4: "current"}, [],
                                          {p2: ["b"], p4: ["a"]})


def test_fx_pb_e3_change_variant_fx_r2_s8(world):
    """W1 (t1) states P from t1; W2 (t5) states I from t5. Between: P current. After: P superseded [t1, t5), I current."""
    g, clock, wp = world["g"], world["clock"], world["wp"]
    clock.t = 1; span(g, "w1", 1); p = _fact(wp, "OWNS", P, LEDGER, 1, "w1", form="prose")
    clock.t = 5; span(g, "w2", 5); i = _fact(wp, "OWNS", I, LEDGER, 5, "w2", form="prose")
    assert both(g, OWNS, 3, 2) == expect(P, False, 1, MAX, [p], {p: "current"}, [], {p: ["w1"]})
    assert both(g, OWNS, 3, 6) == expect(P, False, 1, MAX, [p], {p: "current"}, [], {p: ["w1"]})
    assert both(g, OWNS, 10, 2) == expect(P, False, 1, 5, [p], {p: "superseded"}, [], {p: ["w1"]})
    assert both(g, OWNS, 10, 6) == expect(I, False, 5, MAX, [i], {i: "current"}, [], {i: ["w2"]})


def test_fx_pb_e3_disputed_blocker_variant(world):
    """P@t2 (rank 2); I@t5 (rank 2) supersedes P at r5. A rank-4 P restatement from t5 at r6 makes I disputed.
    At T > r6 / V6, I doesn't block P: P is current (run {P@t2, P@t5}) and I is disputed, open."""
    g, clock, wp = world["g"], world["clock"], world["wp"]
    clock.t = 2; span(g, "w1", 2); p = _fact(wp, "OWNS", P, LEDGER, 2, "w1", form="prose")
    clock.t = 5; span(g, "w2", 5); i = _fact(wp, "OWNS", I, LEDGER, 5, "w2", form="prose")
    clock.t = 6; span(g, "ro", 6); p5 = _fact(wp, "OWNS", P, LEDGER, 5, "ro")
    assert both(g, OWNS, 5, 6) == expect(I, False, 5, MAX, [i], {i: "current"}, [], {i: ["w2"]})
    assert both(g, OWNS, 5, 3) == expect(P, False, 2, 5, [p], {p: "superseded"}, [], {p: ["w1"]})
    assert both(g, OWNS, 7, 6) == expect(P, False, 2, MAX, [p, p5], {p: "current", p5: "current"},
                                         [{"assertion_id": i, "target": p5, "settled": False, "confirmed_at": None}],
                                         {p: ["w1"], p5: ["ro"]})
    assert both(g, OWNS, 7, 3) == both(g, OWNS, 7, 6)


def test_fx_pb_e5_flags_not_timestamps(world):
    """Source S states A from v10 at r10. S is tombstoned at r20 (its evidence gets removed_at, A is retracted).
    T15: A holds with S's evidence. T25: not held. Neither engine reads Source.status."""
    g, clock, wp = world["g"], world["clock"], world["wp"]
    make_span(g, "s_s", "A owns ledger", 10, src="src:S")
    clock.t = 10; a = _fact(wp, "OWNS", A, LEDGER, 10, "s_s")
    clock.t = 20; _retract(wp, a, span_id="s_s")   # the write path's tombstone: S's evidence gets removed_at (02 §5)
    g.write("MATCH (s:Source {id:'src:S'}) SET s.status = 'deleted'")
    assert both(g, OWNS, 15, 15) == expect(A, False, 10, MAX, [a], {a: "current"}, [], {a: ["s_s"]})
    assert both(g, OWNS, 25, 15) is None
    assert g.ro("MATCH (a:Assertion {id:$id}) RETURN a.status AS s", {"id": a})[0]["s"] == "retracted"


def test_fx_r2_s10_open_settled_open_open(world):
    """T1 = 10: challenger I (chat, authored 10). T2 = 20: Priya confirms P. T3 = 30: new I message authored 30.
    T4 = 40: the confirmation is undone. Belief times 15, 25, 35, 45: open, settled, open, open."""
    g, clock, wp, acts = world["g"], world["clock"], world["wp"], world["acts"]
    clock.t = 1; span(g, "ro", 1); p = _fact(wp, "OWNS", P, LEDGER, 2, "ro")
    clock.t = 10; span(g, "m1", 10); i = _fact(wp, "OWNS", I, LEDGER, 3, "m1", form="chat")
    clock.t = 20; res = acts.confirm_fact(actor("person:priya"), assertion_id=p)
    cs = conf_span(g, res)
    clock.t = 30; span(g, "m2", 30); assert _fact(wp, "OWNS", I, LEDGER, 3, "m2", form="chat") == i
    clock.t = 40; acts.undo_action(actor("person:priya"), res["action_id"])
    d = lambda settled, at: [{"assertion_id": i, "target": p, "settled": settled, "confirmed_at": at}]  # noqa: E731
    assert both(g, OWNS, 15, 10) == expect(P, False, 2, MAX, [p], {p: "current"}, d(False, None), {p: ["ro"]})
    assert both(g, OWNS, 25, 10) == expect(P, False, 2, MAX, [p], {p: "current"}, d(True, 20), {p: sorted(["ro", cs])})
    assert both(g, OWNS, 35, 10) == expect(P, False, 2, MAX, [p], {p: "current"}, d(False, 20), {p: sorted(["ro", cs])})
    assert both(g, OWNS, 45, 10) == expect(P, False, 2, MAX, [p], {p: "current"}, d(False, None), {p: ["ro"]})


# FX-PB-RAND: property-based

def current_read(g, cid, v):
    """The current-belief read from stored fields (status/run_id/valid_to), for I6 at T = now."""
    hit = g.ro("MATCH (a:Assertion {chain_id:$c}) WHERE a.status IN ['current','superseded'] "
               "AND a.valid_from <= $V AND a.valid_to > $V RETURN DISTINCT a.run_id AS run", {"c": cid, "V": v})
    if not hit:
        return None
    assert len(hit) == 1
    rows = g.ro("MATCH (m:Assertion {run_id:$r}) WHERE m.status IN ['current','superseded'] "
                "RETURN m.id AS id, m.status AS status, m.valid_from AS vf, m.valid_to AS vt", {"r": hit[0]["run"]})
    return {"run": sorted(r["id"] for r in rows), "states": {r["id"]: r["status"] for r in rows},
            "valid_from": min(r["vf"] for r in rows), "valid_to": rows[0]["vt"]}


_FORMS = {1: "chat", 2: "prose", 4: "structured"}
event_st = st.one_of(
    st.tuples(st.just("add"), st.sampled_from([I, P]), st.integers(1, 6), st.sampled_from([1, 2, 4])),
    st.tuples(st.just("confirm"), st.integers(0, 5)),      # confirmation evidence on the n-th live assertion
    st.tuples(st.just("retract"), st.integers(0, 5)),      # remove one live span of the n-th assertion
)
_counter = itertools.count()


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.lists(event_st, min_size=1, max_size=7))
def test_fx_pb_rand_engines_agree_and_i6(g, events):
    """Random small chains (<= 6 records over two values and ranks {1, 2, 4}, with confirmations and
    retractions in random order): both engines agree at every (T, V), and at T = now they equal the
    current read (I6)."""
    n = next(_counter)
    sysid = f"system:pb{n}"
    store.upsert_entities(g, [{"id": sysid, "name": f"PB{n}", "aliases": []},
                              {"id": I, "name": "Infra", "aliases": []}, {"id": P, "name": "Payments", "aliases": []}])
    cid = registry.chain_id("OWNS", "", "", sysid)
    clock = Clock(1000 * (n + 1))
    wp = WritePath(g, clock)
    aids: list[str] = []
    times: list[int] = []
    adds = 0
    for ev in events:
        clock.tick(2)
        sid = f"rs{n}_{clock()}"
        make_span(g, sid, f"text {sid}", clock())
        if ev[0] == "add":
            if adds >= 6:
                continue
            adds += 1
            _, val, vf, rank = ev
            aid = _fact(wp, "OWNS", val, sysid, vf, sid, form=_FORMS[rank])
            if aid not in aids:
                aids.append(aid)
        elif ev[0] == "confirm":
            if not aids:
                continue
            target = aids[ev[1] % len(aids)]
            m = g.ro("MATCH (a:Assertion {id:$id}) RETURN a.subject_id AS s, a.valid_from AS vf, a.status AS st",
                     {"id": target})[0]
            if m["st"] == "retracted":
                continue
            _fact(wp, "OWNS", m["s"], sysid, m["vf"], sid, form="confirmation")
        else:
            if not aids:
                continue
            target = aids[ev[1] % len(aids)]
            live = g.ro("MATCH (a:Assertion {id:$id})-[e:EVIDENCED_BY]->(s) WHERE e.removed_at = $m "
                        "RETURN s.id AS sid ORDER BY sid LIMIT 1", {"id": target, "m": MAX})
            if live:
                _retract(wp, target, span_id=live[0]["sid"])
        times.append(clock())
    now = clock() + 1
    belief_times = sorted({t - 1 for t in times} | {t for t in times} | {now})
    for t in belief_times:
        for v in range(0, 8):
            r = both(g, cid, t, v)
            if t == now:                                             # I6
                cur = current_read(g, cid, v)
                assert (r is None) == (cur is None), (r, cur)
                if r:
                    assert r["run"] == cur["run"] and r["states"] == cur["states"]
                    assert (r["valid_from"], r["valid_to"]) == (cur["valid_from"], cur["valid_to"])
