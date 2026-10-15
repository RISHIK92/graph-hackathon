import pytest

from brain import registry, templates
from brain.config import MAX
from brain.db import GuardFailed, WriteMismatch
from brain.write_path import Candidate, ValidationError, WritePath, build_query, validate

from .conftest import make_span, seed_basic


def owns(team, span, vf, form, src="src:test"):
    return Candidate("OWNS", team, "system:ledger", valid_from=vf, span_id=span, quote_start=0,
                     quote_end=len(span), form=form, source_id=src)


def apply(wp, *cands, now=None):
    plan = wp.new_plan(now)
    for c in cands:
        wp.add_candidate(plan, c)
    return wp.execute(plan)


def owner_edges(g):
    return g.ro("MATCH (t)-[o:OWNS]->(:System {id:'system:ledger'}) RETURN t.id AS t, o.valid_from AS vf, "
                "o.valid_to AS vt, o.authority AS auth ORDER BY vf")


def statuses(g):
    return {r["s"]: r["st"] for r in g.ro("MATCH (a:Assertion) RETURN a.subject_id AS s, a.status AS st")}


def test_fx_r2_s1_dispute_both_orders(g, clock):
    seed_basic(g)
    make_span(g, "sp_roster", "Payments owns Ledger", 2)
    make_span(g, "sp_chat", "Infra owns Ledger", 3)
    wp = WritePath(g, clock)
    apply(wp, owns("team:payments", "sp_roster", 2, "structured"))
    clock.tick()
    apply(wp, owns("team:infra", "sp_chat", 3, "chat"))
    assert statuses(g) == {"team:payments": "current", "team:infra": "disputed"}
    d = g.ro("MATCH (a:Assertion)-[r:DISPUTES]->(b:Assertion) RETURN a.subject_id AS a, b.subject_id AS b")
    assert d == [{"a": "team:infra", "b": "team:payments"}]
    assert [(r["t"], r["vt"]) for r in owner_edges(g)] == [("team:payments", MAX)]


def test_supersede_and_reingest_noop(g, clock):
    seed_basic(g)
    make_span(g, "s1", "Platform owns Ledger", 1)
    make_span(g, "s2", "Payments owns Ledger", 5)
    wp = WritePath(g, clock)
    apply(wp, owns("team:platform", "s1", 1, "structured"))
    clock.tick()
    apply(wp, owns("team:payments", "s2", 5, "structured"))
    assert [(r["t"], r["vf"], r["vt"]) for r in owner_edges(g)] == [("team:platform", 1, 5), ("team:payments", 5, MAX)]
    v = g.ro("MATCH (c:Chain) RETURN c.version AS v")[0]["v"]
    clock.tick()
    res = apply(wp, owns("team:payments", "s2", 5, "structured"))
    assert res["noop"] is True                                       # I3
    assert g.ro("MATCH (c:Chain) RETURN c.version AS v")[0]["v"] == v


def test_dedup_adds_evidence_only(g, clock):
    seed_basic(g)
    make_span(g, "s1", "Payments owns Ledger", 5)
    make_span(g, "s2", "Payments owns Ledger (wiki)", 6)
    wp = WritePath(g, clock)
    apply(wp, owns("team:payments", "s1", 5, "structured"))
    clock.tick()
    r = apply(wp, owns("team:payments", "s2", 5, "prose"))
    assert r["outcomes"][0]["outcome"] == "dedup"
    assert g.ro("MATCH (a:Assertion) RETURN count(a) AS n")[0]["n"] == 1
    assert g.ro("MATCH ()-[e:EVIDENCED_BY]->() RETURN count(e) AS n")[0]["n"] == 2


def test_retraction_reopens_superseded(g, clock):
    seed_basic(g)
    make_span(g, "s1", "Platform owns Ledger", 1)
    make_span(g, "s2", "Payments owns Ledger", 5)
    wp = WritePath(g, clock)
    apply(wp, owns("team:platform", "s1", 1, "prose"))
    clock.tick()
    r = apply(wp, owns("team:payments", "s2", 5, "prose"))
    aid = r["outcomes"][0]["assertion_id"]
    clock.tick()
    plan = wp.new_plan()
    wp.remove_evidence(plan, aid, span_id="s2")
    wp.execute(plan)
    assert statuses(g) == {"team:platform": "current", "team:payments": "retracted"}
    sup = g.ro("MATCH ()-[r:SUPERSEDES]->() RETURN r.removed_at AS rm")
    assert sup and sup[0]["rm"] != MAX                               # never deleted (A3)


def test_guard_version_race_aborts(g, clock):
    seed_basic(g)
    make_span(g, "s1", "Payments owns Ledger", 5)
    make_span(g, "s2", "Infra owns Ledger", 6)
    wp = WritePath(g, clock)
    stale = wp.new_plan()
    wp.add_candidate(stale, owns("team:infra", "s2", 6, "structured"))   # read version -1
    apply(wp, owns("team:payments", "s1", 5, "structured"))              # concurrent write
    with pytest.raises(GuardFailed):
        wp.execute(stale)
    assert statuses(g) == {"team:payments": "current"}
    assert g.ro("MATCH (s:GuardFail) RETURN count(s) AS n")[0]["n"] == 1


def test_guard_missing_entity_aborts(g, clock):
    """A missing subject entity fires the guard: nothing is written (no partial write before F18)."""
    seed_basic(g)
    make_span(g, "s1", "Platform owns Ledger", 5)
    wp = WritePath(g, clock)
    with pytest.raises(GuardFailed):
        apply(wp, owns("team:ghost", "s1", 5, "structured"))
    assert g.ro("MATCH (a:Assertion) RETURN count(a) AS n")[0]["n"] == 0
    assert g.ro("MATCH (c:Chain) RETURN count(c) AS n")[0]["n"] == 0


def test_zero_row_target_is_failure(g, clock):
    """F18: a MATCH that finds nothing must not look like success."""
    seed_basic(g)
    wp = WritePath(g, clock)
    plan = wp.new_plan()
    wp.add_candidate(plan, owns("team:payments", "sp_missing", 5, "structured"))
    with pytest.raises(WriteMismatch):
        wp.execute(plan)


def test_validation(g):
    seed_basic(g)
    ents = {"team:infra": {"name": "Infra", "aliases": []}, "system:ledger": {"name": "Ledger", "aliases": []}}
    c = Candidate("OWNS", "team:infra", "system:ledger", span_id="x", quote_start=0, quote_end=17, form="chat")
    validate(g, c, ents, "Infra owns Ledger now", learn_fact_session="s")
    with pytest.raises(ValidationError):
        validate(g, c, ents, "Infra owns it now..", learn_fact_session="s")
    with pytest.raises(ValidationError):
        validate(g, Candidate("OWNS", "person:x", "team:infra"), ents, None)


def test_literal_projection(g, clock):
    seed_basic(g)
    make_span(g, "s1", "RDS-42 open", 1)
    make_span(g, "s2", "RDS-42 done", 5)
    wp = WritePath(g, clock)
    apply(wp, Candidate("HAS_STATE", "ticket:rds-42", object_value="open", valid_from=1, span_id="s1",
                        quote_end=6, form="structured"))
    clock.tick()
    apply(wp, Candidate("HAS_STATE", "ticket:rds-42", object_value="done", valid_from=5, span_id="s2",
                        quote_end=6, form="structured"))
    assert g.ro("MATCH (t:Ticket {id:'ticket:rds-42'}) RETURN t.state AS s")[0]["s"] == "done"


def test_build_query_counts_empty_plan(g, clock):
    wp = WritePath(g, clock)
    q, p, expect = build_query(wp.new_plan())
    assert expect == {"nodes": 0, "rels": 0}


def test_read_compiled_before_first_edge_sees_later_edges(g, clock):
    """F23: on 4.22.0 a pattern comprehension cached before its relationship type existed stayed empty."""
    seed_basic(g)
    args = {"chain": registry.chain_id("OWNS", "", "", "system:ledger"), "T": 10**6, "V": 5}
    assert g.ro(templates.body("past_belief_run"), args) == []
    make_span(g, "s1", "Payments owns Ledger", 5)
    apply(WritePath(g, clock), owns("team:payments", "s1", 5, "chat"))
    assert [r["subject_id"] for r in g.ro(templates.body("past_belief_run"), args)] == ["team:payments"]
