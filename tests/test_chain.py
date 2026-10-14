"""Pure chain-function tests: 08 fixtures with hand-written expected results, plus the order property."""
from hypothesis import given, settings, strategies as st

from brain.chain import Evidence, Record, past_belief, walk
from brain.config import MAX

A, B = "team:a", "team:b"            # A < B by value id
P, I = "team:payments", "team:infra"  # I < P


def ev(span, auth, ra, rm=MAX, ts=None, form=None):
    form = form or {4: "structured", 2: "prose", 1: "chat", 0: "draft"}[auth]
    return Evidence(span, form, auth, ra, rm, ts if ts is not None else ra)


def conf(span, ra, rm=MAX):
    return Evidence(span, "confirmation", 4, ra, rm, ra)


def rec(i, value, vf, ra, evidence, rt=MAX, neg=False):
    return Record(i, value, neg, vf, ra, rt, evidence)


def test_r2_s1_order_independent_dispute():
    recs = [rec("p", P, 2, 1, [ev("s1", 4, 1)]), rec("i", I, 3, 2, [ev("s2", 1, 2)])]
    for order in (recs, recs[::-1]):
        s = walk(order, 100)
        assert s.status == {"p": "current", "i": "disputed"}
        assert s.disputes == {("i", "p")}


def test_r1_s2_equal_date_equal_rank_value_id_wins():
    a = rec("a", A, 10, 1, [ev("sp_9", 2, 1), ev("sp_8", 2, 2)])
    b = rec("b", B, 10, 3, [ev("sp_1", 2, 3)])
    for order in ([a, b], [b, a]):
        s = walk(order, 100)
        assert s.status["a"] == "current" and s.status["b"] == "disputed"


def test_r2_s2_infra_wins_tie_then_confirm_payments():
    p = rec("p", P, 3, 1, [ev("w1", 2, 1)])
    i = rec("i", I, 3, 1, [ev("w2", 2, 1)])
    s = walk([p, i], 10)
    assert s.status == {"i": "current", "p": "disputed"}
    p.evidence.append(conf("c", 20))
    s = walk([p, i], 30)
    assert s.status == {"p": "current", "i": "disputed"}
    r = past_belief([p, i], 30, 5)
    assert r["value"] == P and r["disputes"][0]["settled"] is True


def test_r1_s3_confirm_challenger_then_undo():
    a = rec("a", A, 10, 1, [ev("sa", 4, 1)])
    b = rec("b", B, 20, 2, [ev("sb", 1, 2)])
    b.evidence.append(conf("cb", 30, rm=40))
    after = walk([a, b], 35)
    assert after.status == {"a": "superseded", "b": "current"} and after.valid_to["a"] == 20
    assert past_belief([a, b], 25, 25)["value"] == A
    assert past_belief([a, b], 25, 25)["disputes"][0]["settled"] is False
    undone = walk([a, b], 45)
    assert undone.status == {"a": "current", "b": "disputed"}


def test_r1_s4_confirm_recorded_side_settles_then_undo_reopens():
    a = rec("a", A, 10, 1, [ev("sa", 4, 1), conf("ca", 30, rm=40)])
    b = rec("b", B, 20, 2, [ev("sb", 1, 2)])
    r = past_belief([a, b], 35, 35)
    assert r["value"] == A and r["disputes"] == [{"assertion_id": "b", "target": "a", "settled": True, "confirmed_at": 30}]
    assert past_belief([a, b], 45, 45)["disputes"][0]["settled"] is False


def test_r1_s10_later_smaller_span_does_not_move_winner():
    a = rec("a", A, 10, 10, [ev("sp_50", 2, 10), ev("sp_10", 2, 40)])
    b = rec("b", B, 10, 20, [ev("sp_30", 2, 20)])
    for t in (25, 45):
        assert walk([a, b], t).status == {"a": "current", "b": "disputed"}
    assert past_belief([a, b], 30, 30)["evidence"]["a"] == ["sp_50"]


def test_r1_s11_run_rebuilt_settled():
    a1 = rec("a1", A, 10, 1, [ev("x", 4, 1), conf("c", 20)])
    b = rec("b", B, 15, 2, [ev("y", 1, 2)])
    a2 = rec("a2", A, 25, 30, [ev("z", 4, 30)])
    r = past_belief([a1, b, a2], 35, 30)
    assert r["run"] == ["a1", "a2"] and r["valid_from"] == 10 and r["valid_to"] == MAX
    assert r["disputes"][0]["settled"] is True


def test_r1_s14_negation_chain():
    plus = rec("p", "", 10, 1, [ev("s", 2, 1)])
    minus = rec("m", "", 20, 1, [ev("s", 2, 1)], neg=True)
    assert past_belief([plus, minus], 50, 15)["negated"] is False
    assert past_belief([plus, minus], 50, 25)["negated"] is True


def test_pb4_superseder_retraction():
    a = rec("a", A, 10, 10, [ev("sa", 2, 10)])
    b = rec("b", B, 20, 20, [ev("sb", 2, 20)], rt=30)
    assert past_belief([a, b], 25, 25)["value"] == B
    r = past_belief([a, b], 35, 25)
    assert r["value"] == A and (r["valid_from"], r["valid_to"]) == (10, MAX)


def test_pb_e1_settledness_scope():
    p2 = rec("p2", P, 2, 1, [ev("r1", 4, 1), conf("c", 3)])
    i3 = rec("i3", I, 3, 2, [ev("ch", 1, 2, ts=2)])
    p4 = rec("p4", P, 4, 4, [ev("r2", 4, 4)])
    r = past_belief([p2, i3, p4], 100, 5)
    assert r["run"] == ["p2", "p4"] and r["valid_from"] == 2 and r["disputes"][0]["settled"] is True


def test_pb_e2_run_at_t():
    p4 = rec("p4", P, 4, 1, [ev("a", 4, 1)])
    p2 = rec("p2", P, 2, 2, [ev("b", 4, 2)])
    assert past_belief([p4, p2], 1, 5)["run"] == ["p4"]
    r = past_belief([p4, p2], 3, 5)
    assert r["run"] == ["p2", "p4"] and r["valid_from"] == 2


def test_pb_e3_disputed_blocker():
    p = rec("p", P, 2, 2, [ev("w1", 2, 2)])
    i = rec("i", I, 5, 5, [ev("w2", 2, 5)])
    p5 = rec("p5", P, 5, 6, [ev("ro", 4, 6)])
    assert past_belief([p, i, p5], 5.5, 6)["value"] == I
    r = past_belief([p, i, p5], 7, 6)
    assert r["value"] == P and r["states"]["p"] == "current"
    assert walk([p, i, p5], 7).status["i"] == "disputed"


def test_pb_e5_tombstone_by_edges_only():
    a = rec("a", A, 10, 10, [ev("s", 4, 10, rm=20)], rt=20)
    assert past_belief([a], 15, 15)["value"] == A
    assert past_belief([a], 25, 15) is None


def test_r1_s15_and_r2_s10_settled_open_cycle():
    p = rec("p", P, 2, 1, [ev("ro", 4, 1)])
    i = rec("i", I, 3, 1, [ev("m1", 1, 1, ts=1)])
    p.evidence.append(conf("c", 2, rm=4))
    i.evidence.append(ev("m2", 1, 3, ts=3))
    states = [past_belief([p, i], t, 10)["disputes"][0]["settled"] for t in (1.5, 2.5, 3.5, 4.5)]
    assert states == [False, True, False, False]
    assert past_belief([p, i], 2.5, 10)["evidence"]["p"] == ["c", "ro"]


def test_backfill_does_not_reopen_settled():
    """A56: evidence authored before the confirmation but ingested after it keeps the dispute settled."""
    p = rec("p", P, 2, 1, [ev("ro", 4, 1), conf("c", 5)])
    i = rec("i", I, 3, 1, [ev("m1", 1, 1, ts=1), ev("old", 1, 9, ts=4)])
    assert past_belief([p, i], 10, 10)["disputes"][0]["settled"] is True


def test_proposed_never_joins():
    prop = rec("x", B, 5, 5, [ev("d", 0, 5)])
    a = rec("a", A, 1, 1, [ev("s", 4, 1)])
    s = walk([a, prop], 10)
    assert s.status == {"a": "current", "x": "proposed"} and not s.disputes and not s.supersedes


# property: the chain walk is order-independent and I6 holds

record_st = st.builds(
    lambda vals: vals,
    st.lists(st.tuples(st.sampled_from([A, B]), st.integers(1, 6), st.sampled_from([1, 2, 4])),
             min_size=1, max_size=6, unique_by=lambda x: (x[0], x[1])))


@settings(max_examples=200, deadline=None)
@given(record_st, st.randoms())
def test_order_independent(specs, rnd):
    recs = [rec(f"r{i}", v, vf, i + 1, [ev(f"s{i}", au, i + 1)]) for i, (v, vf, au) in enumerate(specs)]
    base = walk(recs, 100)
    shuffled = recs[:]
    rnd.shuffle(shuffled)
    other = walk(shuffled, 100)
    assert base.status == other.status and base.valid_to == other.valid_to
    assert base.supersedes == other.supersedes and base.disputes == other.disputes
    # I6: a past-belief read at T = now equals the current walk
    for v in range(0, 8):
        r = past_belief(recs, 100, v)
        cur = [run for run in base.runs if run.valid_from <= v < run.valid_to]
        assert (r is None) == (not cur)
        if r:
            assert r["run"] == sorted(cur[0].members)
