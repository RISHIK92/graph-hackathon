from dataclasses import replace

from brain import tools
from brain.actions import Actions, Actor
from brain.config import settings
from brain.tools import Ctx, run_tool

from .conftest import make_span
from .test_actions import _fact, world  # noqa: F401  (fixture)


def _all_spans(pack):
    return [s for it in pack["items"] for s in it["spans"]]


def test_get_owner_with_open_dispute(world):
    g, clock, wp = world["g"], world["clock"], world["wp"]
    ch = _fact(wp, "OWNS", "team:infra", "system:ledger", 3, "sp6", form="chat")
    pack = run_tool(Ctx(g, now=clock()), "get_owner", {"entity_id": "system:ledger"})
    top = pack["items"][0]
    owns = [f for f in top["facts"] if f["predicate"] == "OWNS"][0]
    assert owns["subject_id"] == "team:payments" and owns["status"] == "current"
    assert owns["open_disputes"] == [ch]                                         # D5
    assert [s["node"]["id"] for s in top["path"]["steps"]] == ["system:ledger", "team:payments", "person:priya"]
    assert any(it["note"] == "open dispute" and it["facts"][0]["assertion_id"] == ch for it in pack["items"])
    assert all(s["live"] for s in top["spans"])


def test_settled_dispute_not_open_and_overruled(world):
    g, clock, wp = world["g"], world["clock"], world["wp"]
    ch = _fact(wp, "OWNS", "team:infra", "system:ledger", 3, "sp6", form="chat")
    clock.tick()
    Actions(g, clock).confirm_fact(Actor("person:priya"), assertion_id=world["ids"]["own_p"])
    clock.tick()
    pack = run_tool(Ctx(g, now=clock()), "get_owner", {"entity_id": "system:ledger"})
    owns = [f for f in pack["items"][0]["facts"] if f["predicate"] == "OWNS"][0]
    assert owns["open_disputes"] == []
    hist = run_tool(Ctx(g, now=clock()), "get_history", {"entity_id": "system:ledger", "predicate": "OWNS"})
    d = [f for f in hist["items"][0]["facts"] if f["assertion_id"] == ch][0]
    assert d["status"] == "disputed" and "overruled_by" in d


def test_past_belief_owner(world):
    g, clock, wp = world["g"], world["clock"], world["wp"]
    t_before = clock()
    clock.tick()
    make_span(g, "sp_new", "catalog v2", 2)
    _fact(wp, "OWNS", "team:infra", "system:ledger", 50, "sp_new")
    now = clock.tick()
    cur = run_tool(Ctx(g, now=now), "get_owner", {"entity_id": "system:ledger"})
    assert cur["items"][0]["facts"][0]["subject_id"] == "team:infra"
    past = run_tool(Ctx(g, now=now, belief_at=t_before, as_of=60), "get_owner", {"entity_id": "system:ledger"})
    assert past["items"][0]["facts"][0]["subject_id"] == "team:payments"


def test_cypher_engine_matches_python_on_as_of_reads(world, monkeypatch):
    """PAST_BELIEF_ENGINE=cypher (A38, A46): the Cypher engine runs without falling back and the packs
    equal the Python reference's, on both versions."""
    g, clock, wp = world["g"], world["clock"], world["wp"]
    t_before = clock()
    clock.tick()
    make_span(g, "sp_new", "catalog v2", 2)
    _fact(wp, "OWNS", "team:infra", "system:ledger", 50, "sp_new")
    now = clock.tick()
    real, calls = tools.past_belief_cypher, []

    def spy(*a):
        calls.append(real(*a))
        return calls[-1]
    monkeypatch.setattr(tools, "past_belief_cypher", spy)
    for t, v in ((t_before, 60), (now, 60), (now, 10)):
        ctx = lambda: Ctx(g, now=now, belief_at=t, as_of=v)  # noqa: E731
        monkeypatch.setattr(tools, "settings", replace(settings, past_belief_engine="python"))
        ref = run_tool(ctx(), "get_owner", {"entity_id": "system:ledger"})
        monkeypatch.setattr(tools, "settings", replace(settings, past_belief_engine="cypher"))
        n = len(calls)
        assert run_tool(ctx(), "get_owner", {"entity_id": "system:ledger"}) == ref
        assert len(calls) > n and calls[-1] is not None


def test_draft_spans_never_in_packs(world):
    g, clock = world["g"], world["clock"]
    acts = Actions(g, clock)
    r = acts.route_to_owner(Actor("person:eve"), ticket_id="ticket:rds-42")
    pack = run_tool(Ctx(g, now=clock()), "get_history", {"entity_id": "ticket:rds-42", "predicate": "ASSIGNED_TO"})
    facts = [f for it in pack["items"] for f in it["facts"]]
    assert facts and facts[0]["status"] == "proposed" and facts[0]["action_id"] == r["action_id"]
    assert all(s["kind"] != "draft" for s in _all_spans(pack))
    assert pack["items"][0]["actions"][0]["action_id"] == r["action_id"]


def test_explain_action_then_now(world):
    g, clock, wp = world["g"], world["clock"], world["wp"]
    acts = Actions(g, clock)
    r = acts.route_to_owner(Actor("person:eve"), ticket_id="ticket:rds-42")
    clock.tick()
    make_span(g, "sp_new", "catalog v2", 2)
    _fact(wp, "OWNS", "team:infra", "system:ledger", clock(), "sp_new")
    clock.tick()
    pack = run_tool(Ctx(g, now=clock()), "explain_action", {"action_id": r["action_id"]})
    it = pack["items"][0]
    then = {f["subject_id"]: f["status"] for f in it["then_now"]["then"]["based_on"] if f["predicate"] == "OWNS"}
    now = {f["subject_id"]: f["status"] for f in it["then_now"]["now"]["based_on"] if f["predicate"] == "OWNS"}
    assert then == {"team:payments": "current"} and now == {"team:payments": "superseded"}
    assert it["changed_since"]


def test_impact_mode(world):
    g, clock, wp = world["g"], world["clock"], world["wp"]
    from brain import store
    store.upsert_entities(g, [{"id": "system:billing", "name": "Billing", "aliases": []},
                              {"id": "system:invoices", "name": "Invoices", "aliases": []}])
    make_span(g, "d1", "billing depends on ledger", 1)
    make_span(g, "d2", "invoices depends on billing", 1)
    make_span(g, "d3", "infra owns billing", 1)
    _fact(wp, "DEPENDS_ON", "system:billing", "system:ledger", 1, "d1")
    _fact(wp, "DEPENDS_ON", "system:invoices", "system:billing", 1, "d2")
    _fact(wp, "OWNS", "team:infra", "system:billing", 1, "d3")
    pack = run_tool(Ctx(g, now=clock.tick()), "find_paths", {"from_id": "system:ledger"})
    tails = [[s["node"]["id"] for s in it["path"]["steps"]] for it in pack["items"] if it["path"]]
    assert ["system:ledger", "team:payments", "person:priya"] in tails
    assert ["system:ledger", "system:billing", "team:infra", "person:bob"] in tails
    assert any(t[:3] == ["system:ledger", "system:billing", "system:invoices"] for t in tails)


def test_link_entities_and_search(world):
    g, clock = world["g"], world["clock"]
    pack = run_tool(Ctx(g, now=clock()), "link_entities", {"mentions": ["ledger-service", "Priya"]})
    assert pack["items"][0]["rows"][0]["entity_id"] == "system:ledger"
    assert pack["items"][1]["rows"][0]["entity_id"] == "person:priya"
