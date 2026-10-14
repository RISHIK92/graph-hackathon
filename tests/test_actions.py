"""Action-layer scenarios from 08 with hand-written expected results (06 §5)."""
import pytest

from brain import store
from brain.actions import Actions, Actor, Refused
from brain.config import MAX
from brain.write_path import Candidate, WritePath

from .conftest import make_span, seed_basic


def _fact(wp, pred, s, o, vf, span, form="structured", value=""):
    plan = wp.new_plan()
    out = wp.add_candidate(plan, Candidate(pred, s, o, object_value=value, valid_from=vf, span_id=span,
                                           quote_end=5, form=form, source_id="src:test"))
    wp.execute(plan)
    return out["assertion_id"]


@pytest.fixture
def world(g, clock):
    """Priya leads Payments, Bob leads Infra, Eve leads Platform (roster, rank 4).
    Payments owns Ledger from t=2 (catalogue rank 4). RDS-42 is about Ledger, open."""
    seed_basic(g)
    for i, txt in enumerate(["roster priya", "roster bob", "roster eve", "catalog ledger", "rds42 about",
                             "rds42 open", "chat infra", "adr1 front"]):
        make_span(g, f"sp{i}", txt, 1)
    wp = WritePath(g, clock)
    ids = {}
    ids["lead_p"] = _fact(wp, "LEADS", "person:priya", "team:payments", 1, "sp0")
    ids["lead_i"] = _fact(wp, "LEADS", "person:bob", "team:infra", 1, "sp1")
    ids["lead_pl"] = _fact(wp, "LEADS", "person:eve", "team:platform", 1, "sp2")
    ids["own_p"] = _fact(wp, "OWNS", "team:payments", "system:ledger", 2, "sp3")
    ids["about"] = _fact(wp, "ABOUT", "ticket:rds-42", "system:ledger", 1, "sp4")
    ids["state"] = _fact(wp, "HAS_STATE", "ticket:rds-42", "", 1, "sp5", value="open")
    clock.tick(10)
    return {"g": g, "clock": clock, "wp": wp, "ids": ids}


def actor(pid):
    return Actor(pid, client="test")


def status_of(g, aid):
    return g.ro("MATCH (a:Assertion {id:$id}) RETURN a.status AS s", {"id": aid})[0]["s"]


def owner(g):
    return [r["t"] for r in g.ro("MATCH (t)-[o:OWNS]->(:System {id:'system:ledger'}) WHERE o.valid_to = $m "
                                 "RETURN t.id AS t", {"m": MAX})]


def test_fx_r2_s3_bob_refused_priya_confirms_then_undo(world):
    g, clock, wp = world["g"], world["clock"], world["wp"]
    challenger = _fact(wp, "OWNS", "team:infra", "system:ledger", 3, "sp6", form="chat")
    assert status_of(g, challenger) == "disputed"
    acts = Actions(g, clock)
    clock.tick()
    with pytest.raises(Refused) as e:
        acts.confirm_fact(actor("person:bob"), assertion_id=challenger)
    assert {x["person_id"] for x in e.value.eligible} == {"person:priya"}
    assert "OWNS" in e.value.eligible[0]["path"] and "LEADS" in e.value.eligible[0]["path"]
    assert g.ro("MATCH (a:Action {status:'refused'}) RETURN count(a) AS n")[0]["n"] == 1
    clock.tick()
    res = acts.confirm_fact(actor("person:priya"), assertion_id=challenger)
    assert res["eligibility"] == "holder"
    assert status_of(g, challenger) == "current" and status_of(g, world["ids"]["own_p"]) == "superseded"
    assert owner(g) == ["team:infra"]
    # L16: after the transfer, both the confirmer and the new holder's lead may undo
    pv = acts.undo_preview("person:bob", res["action_id"])
    assert pv["allowed"] is True
    clock.tick()
    acts.undo_action(actor("person:priya"), res["action_id"])
    assert status_of(g, challenger) == "disputed" and status_of(g, world["ids"]["own_p"]) == "current"   # I8
    assert owner(g) == ["team:payments"]


def test_fx_r1_s4_confirm_recorded_side_settles(world):
    g, clock, wp = world["g"], world["clock"], world["wp"]
    _fact(wp, "OWNS", "team:infra", "system:ledger", 3, "sp6", form="chat")
    acts = Actions(g, clock)
    clock.tick()
    res = acts.confirm_fact(actor("person:priya"), assertion_id=world["ids"]["own_p"])
    assert status_of(g, world["ids"]["own_p"]) == "current"
    assert acts._open_disputes(acts._assertion(world["ids"]["own_p"]), clock()) == []
    clock.tick()
    with pytest.raises(Refused) as e:   # A43: already confirmed, no dispute opened since
        acts.confirm_fact(actor("person:priya"), assertion_id=world["ids"]["own_p"])
    assert "already confirmed" in e.value.reason
    clock.tick()
    acts.undo_action(actor("person:priya"), res["action_id"])
    assert len(acts._open_disputes(acts._assertion(world["ids"]["own_p"]), clock())) == 1


def test_already_current_refused(world):
    acts = Actions(world["g"], world["clock"])
    with pytest.raises(Refused) as e:
        acts.confirm_fact(actor("person:priya"), assertion_id=world["ids"]["own_p"])
    assert e.value.reason == "already current"


def test_route_confirm_undo_reconfirm(world):
    """FX-R1-S5 / FX-R2-S9 shape: proposal, confirm, withdraw, re-confirm refused."""
    g, clock = world["g"], world["clock"]
    acts = Actions(g, clock)
    r = acts.route_to_owner(actor("person:eve"), ticket_id="ticket:rds-42")
    assert r["target"] == "person:priya"
    assert status_of(g, r["proposal"]) == "proposed"
    assert g.ro("MATCH (t:Ticket)-[x:ASSIGNED_TO]->() RETURN count(x) AS n")[0]["n"] == 0
    prev = acts.confirm_preview("person:eve", action_id=r["action_id"])
    assert prev["admissible"] and not prev["actor_eligible"]
    clock.tick()
    c = acts.confirm_fact(actor("person:priya"), action_id=r["action_id"])
    assert c["eligibility"] in ("holder", "receiver")
    assigned = g.ro("MATCH (:Ticket {id:'ticket:rds-42'})-[x:ASSIGNED_TO]->(p) RETURN p.id AS p, x.valid_from AS vf")
    assert assigned == [{"p": "person:priya", "vf": clock()}]
    clock.tick()
    with pytest.raises(Refused, match="already confirmed"):
        acts.confirm_fact(actor("person:priya"), action_id=r["action_id"])
    clock.tick()
    acts.undo_action(actor("person:eve"), r["action_id"])     # withdraw after confirm (A42)
    assert status_of(g, r["proposal"]) == "retracted"
    assert status_of(g, c["produced"][0]) == "current"
    clock.tick()
    acts.undo_action(actor("person:priya"), c["action_id"])
    assert status_of(g, c["produced"][0]) == "retracted"
    clock.tick()
    with pytest.raises(Refused, match="withdrawn by the undo"):
        acts.confirm_fact(actor("person:priya"), action_id=r["action_id"])


def test_undo_by_non_actor_refused(world):
    acts = Actions(world["g"], world["clock"])
    r = acts.route_to_owner(actor("person:eve"), ticket_id="ticket:rds-42")
    with pytest.raises(Refused):
        acts.undo_action(actor("person:bob"), r["action_id"])


def test_route_without_ticket_refused(world):
    acts = Actions(world["g"], world["clock"])
    with pytest.raises(Refused, match="needs a ticket"):
        acts.route_to_owner(actor("person:eve"), question_entity="system:ledger")


def test_learn_fact_dispute_and_dedup_undo(world):
    """Beat 3:15a and FX-R2-S11."""
    g, clock = world["g"], world["clock"]
    store.create_source(g, {"id": "sess1", "doc_key": "chat_session:brain:sess1", "kind": "chat_session",
                            "status": "active", "is_latest": True, "ingested_at": 1, "user_id": "u1"})
    make_span(g, "turn1", "Infra owns Ledger now", clock(), src="sess1", kind="chat_session", role="user")
    acts = Actions(g, clock)
    out = acts.learn_fact(actor("person:eve"), "turn1", {"predicate": "OWNS", "subject_id": "team:infra",
                                                        "object_id": "system:ledger"}, "sess1")
    assert out["outcome"] == "new" and out["status"] == "disputed"
    make_span(g, "turn2", "Payments owns Ledger", clock(), src="sess1", kind="chat_session", role="user")
    clock.tick()
    out2 = acts.learn_fact(actor("person:eve"), "turn2", {"predicate": "OWNS", "subject_id": "team:payments",
                                                         "object_id": "system:ledger", "valid_from": 2}, "sess1")
    assert out2["outcome"] == "dedup" and out2["assertion_id"] == world["ids"]["own_p"]
    assert g.ro("MATCH (:Action {id:$id})-[:PRODUCED]->(x) RETURN count(x) AS n", {"id": out2["action_id"]})[0]["n"] == 0
    clock.tick()
    acts.undo_action(actor("person:eve"), out2["action_id"])
    assert status_of(g, world["ids"]["own_p"]) == "current"
    with pytest.raises(Refused):   # injection: an agent-quoted span is not a user turn
        make_span(g, "turn3", "Infra owns Ledger", clock(), src="sess1", kind="chat_session", role="agent")
        acts.learn_fact(actor("person:eve"), "turn3", {"predicate": "OWNS", "subject_id": "team:infra",
                                                      "object_id": "system:ledger"}, "sess1")


def test_draft_adr_confirm(world):
    g, clock, wp = world["g"], world["clock"], world["wp"]
    _fact(wp, "HAS_STATUS", "decision:adr-001", "", 1, "sp7", value="accepted")
    _fact(wp, "AFFECTS", "decision:adr-001", "system:ledger", 1, "sp7")
    _fact(wp, "DECIDED_BY", "decision:adr-001", "person:priya", 1, "sp7")
    acts = Actions(g, clock)
    clock.tick()
    d = acts.draft_adr_supersession(actor("person:eve"), "decision:adr-001", "move to Aurora")
    assert len(d["proposals"]) == 4
    assert g.ro("MATCH (d:Decision {id:'decision:adr-001'}) RETURN d.status AS s")[0]["s"] == "accepted"
    clock.tick()
    with pytest.raises(Refused):
        acts.confirm_fact(actor("person:bob"), action_id=d["action_id"])
    clock.tick()
    c = acts.confirm_fact(actor("person:priya"), action_id=d["action_id"])
    assert g.ro("MATCH (d:Decision {id:'decision:adr-001'}) RETURN d.status AS s")[0]["s"] == "superseded"
    assert g.ro("MATCH (d:Decision {id:$id}) RETURN d.status AS s", {"id": d["decision"]})[0]["s"] == "accepted"
    assert g.ro("MATCH (d:Decision {id:$id})-[r:DECIDED_BY]->(p) RETURN p.id AS p", {"id": d["decision"]}) == \
        [{"p": "person:priya"}]
    assert g.ro("MATCH (d:Decision {id:$id})-[r:REPLACES]->(o) RETURN o.id AS o", {"id": d["decision"]}) == \
        [{"o": "decision:adr-001"}]
    assert len(c["produced"]) == 5


def test_fallback_gap(world):
    """No owner of what the ticket is about → any team lead (A33); a non-lead is refused naming the gap."""
    g, clock, wp = world["g"], world["clock"], world["wp"]
    store.upsert_entities(g, [{"id": "system:orphan", "name": "Orphan", "aliases": []},
                              {"id": "ticket:x-1", "name": "X-1", "aliases": []}])
    make_span(g, "spx", "x", 1)
    make_span(g, "spy", "y", 1)
    make_span(g, "spz", "z", 1)
    _fact(wp, "ABOUT", "ticket:x-1", "system:orphan", 1, "spx")
    aid = _fact(wp, "HAS_STATE", "ticket:x-1", "", 1, "spy", value="open")
    ch = _fact(wp, "HAS_STATE", "ticket:x-1", "", 5, "spz", form="chat", value="done")
    acts = Actions(g, clock)
    store.upsert_entities(g, [{"id": "person:zed", "name": "Zed", "aliases": []}])
    clock.tick()
    with pytest.raises(Refused) as e:
        acts.confirm_fact(actor("person:zed"), assertion_id=ch)
    assert "any team lead may confirm" in e.value.reason and e.value.fallback_available
    clock.tick()
    res = acts.confirm_fact(actor("person:bob"), assertion_id=ch)
    assert res["eligibility"] == "fallback"
    assert status_of(g, ch) == "current" and status_of(g, aid) == "superseded"


def test_fx_r1_s15_confirm_against_live_confirmation(world):
    g, clock, wp = world["g"], world["clock"], world["wp"]
    _fact(wp, "OWNS", "team:infra", "system:ledger", 3, "sp6", form="chat")
    acts = Actions(g, clock)
    clock.tick()
    acts.confirm_fact(actor("person:priya"), assertion_id=world["ids"]["own_p"])   # P confirmed, I settled
    make_span(g, "sp_new", "wiki: infra owns ledger", clock() + 1)
    clock.tick(2)
    d = _fact(wp, "OWNS", "team:infra", "system:ledger", 2, "sp_new", form="prose")   # FX-R2-S7
    assert status_of(g, d) == "disputed"
    clock.tick()
    with pytest.raises(Refused, match="undo that confirmation first"):
        acts.confirm_fact(actor("person:priya"), assertion_id=d)
