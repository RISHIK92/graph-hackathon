"""06 §5 "Demo script": the Ledger sequence of 07 §4.2 from an isolated seed, with hand-written gold.

Also the preflight of 07 §4.3 on the fresh seed. Uses the real seed-1 render (~10 s to rebuild).
"""
import json
import uuid

import pytest

from api.agent import Agent
from brain.actions import Actions, Actor
from brain.cli import DEFAULT_SEED, reset_seed
from brain.config import MAX
from brain.db import Graph
from brain.tools import Ctx, run_tool
from mcp_server import server as mcp

from .test_agent import shown

LEDGER, PAYMENTS, INFRA, PLATFORM = "system:ledger", "team:payments", "team:infra", "team:platform"
PRIYA, BOB, JONAH = "person:priya-raman", "person:bob-lindqvist", "person:jonah-feld"
RDS42 = "ticket:rds-42"


@pytest.fixture(scope="module")
def seed():
    g = Graph(name=f"demo_{uuid.uuid4().hex[:6]}")
    out = reset_seed(g, str(DEFAULT_SEED))
    assert out["integrity"]["ok"], out["integrity"]
    assert out["cache_hit_rate"] in (None, 1.0), out["cache_hit_rate"]   # preflight: no uncached extraction (07 §4.3)
    yield g
    g.delete()


def owner_facts(g):
    p = run_tool(Ctx(g), "get_owner", {"entity_id": LEDGER})
    return [f for f in p["items"][0]["facts"] if f["predicate"] == "OWNS"][0]


def test_preflight(seed):
    g = seed
    f = owner_facts(g)
    assert f["subject_id"] == PAYMENTS and f["open_disputes"] == []
    assert not g.ro("MATCH (a:Assertion {predicate:'OWNS', subject_id:$i, object_id:$l}) RETURN a",
                    {"i": INFRA, "l": LEDGER})
    t = g.ro("MATCH (t:Ticket {id:$t}) OPTIONAL MATCH (t)-[a:ASSIGNED_TO]->() RETURN t.state AS s, count(a) AS n",
             {"t": RDS42})[0]
    assert t == {"s": "open", "n": 0}
    assert g.ro("MATCH (a:Action) RETURN count(a) AS n")[0]["n"] == 0
    ch = g.ro("MATCH (a:Assertion {object_id:'system:statements', predicate:'OWNS'}) WHERE a.status = 'disputed' "
              "RETURN a.id AS id")
    assert len(ch) == 1                                  # anchor_wrong_challenger is open (G11)
    assert g.ro("MATCH (s:Source {id:'world_meta'}) RETURN s.demo_identity AS d")[0]["d"] == JONAH


def test_demo_sequence(seed):
    g = seed
    agent = Agent(g)
    acts = Actions(g)
    s = agent.create_session("judge", JONAH)

    # (1) owner is Payments, no dispute
    ev = list(agent.turn(s, "Who owns Ledger?"))
    lines = shown(next(e for e in ev if e["event"] == "answer"))
    assert lines[0]["text"].startswith("Payments owns Ledger.") and lines[0]["status"] == "current", lines

    # (2) routing RDS-42 proposes the Payments lead; she is eligible as holder, Jonah is not
    ev = list(agent.turn(s, "Route RDS-42 to the owner"))
    act = next(e for e in ev if e["event"] == "action")
    assert act["result"]["target"] == PRIYA
    route_id = act["action_id"]
    assert not acts.confirm_preview(JONAH, action_id=route_id)["actor_eligible"]
    pv = acts.confirm_preview(PRIYA, action_id=route_id)
    assert pv["admissible"] and pv["actor_eligible"]
    c = acts.confirm_fact(Actor(PRIYA, client="judge", session_source_id=s.id), action_id=route_id)
    assert c["eligibility"] == "holder"
    assert g.ro("MATCH (:Ticket {id:$t})-[a:ASSIGNED_TO]->(p) WHERE a.valid_to = $m RETURN p.id AS p",
                {"t": RDS42, "m": MAX}) == [{"p": PRIYA}]

    # (3) MCP get_owner(ledger-service) returns the same pack as in-app (except pack_id)
    mcp.G = g
    linked = json.loads(mcp.link_entities(["ledger-service"]))["pack"]["items"][0]["rows"][0]["entity_id"]
    assert linked == LEDGER
    a = json.loads(mcp.get_owner(LEDGER))["pack"]
    b = run_tool(Ctx(g), "get_owner", {"entity_id": LEDGER})
    strip = lambda p: [[f["assertion_id"] for f in it["facts"]] for it in p["items"]]  # noqa: E731
    assert strip(a) == strip(b)

    # (4) learn_fact on "Infra owns Ledger now": one rank-1 OWNS, disputed against Payments' run
    ev = list(agent.turn(s, "Infra owns Ledger now"))
    lf = next(e for e in ev if e["event"] == "action")
    assert lf["result"]["outcome"] == "new" and lf["result"]["status"] == "disputed"
    challenger = lf["result"]["assertion_id"]

    # (5) get_owner: Payments plus that open dispute; only the Payments lead may confirm
    f = owner_facts(g)
    assert f["subject_id"] == PAYMENTS and f["open_disputes"] == [challenger]
    el = acts.confirm_preview(BOB, assertion_id=challenger)
    assert {e["person_id"] for e in el["eligible"]} == {PRIYA} and not el["actor_eligible"]

    # (6) she confirms the challenger: Infra current from the turn's ts, Payments superseded at it
    turn_ts = g.ro("MATCH (a:Assertion {id:$a}) RETURN a.valid_from AS v", {"a": challenger})[0]["v"]
    conf = acts.confirm_fact(Actor(PRIYA, client="judge", session_source_id=s.id), assertion_id=challenger)
    assert conf["eligibility"] == "holder"
    f = owner_facts(g)
    assert f["subject_id"] == INFRA and f["valid_from"] == turn_ts
    pay = g.ro("MATCH (a:Assertion {predicate:'OWNS', subject_id:$p, object_id:$l}) WHERE a.status = 'superseded' "
               "RETURN DISTINCT a.valid_to AS vt", {"p": PAYMENTS, "l": LEDGER})
    assert {r["vt"] for r in pay} == {turn_ts}

    # (7) the routing's action view: then Payments owned Ledger, now Infra does
    it = run_tool(Ctx(g), "explain_action", {"action_id": route_id})["items"][0]
    then = {x["subject_id"]: x["status"] for x in it["then_now"]["then"]["based_on"] if x["predicate"] == "OWNS"}
    now = {x["subject_id"]: x["status"] for x in it["then_now"]["now"]["based_on"] if x["predicate"] == "OWNS"}
    assert then[PAYMENTS] == "current" and now[PAYMENTS] == "superseded"

    # (8) graph at D_reorg - 1 day vs D_reorg: Platform then Payments
    d = 1775001600000
    owners = lambda V: {r["o"] for r in g.ro("MATCH (o)-[e:OWNS]->(:System {id:$l}) WHERE e.valid_from <= $V AND "  # noqa: E731
                                              "e.valid_to > $V RETURN o.id AS o", {"l": LEDGER, "V": V})}
    assert owners(d - 86_400_000) == {PLATFORM} and owners(d) == {PAYMENTS}

    # (9) not filmed: undo the confirm; disputed again
    acts.undo_action(Actor(PRIYA, client="judge", session_source_id=s.id), conf["action_id"])
    f = owner_facts(g)
    assert f["subject_id"] == PAYMENTS and f["open_disputes"] == [challenger]


def test_readme_wrong_challenger(seed):
    """D2-W: confirm the recorded owner of Statements; the dispute settles and the answer is unchanged."""
    g = seed
    rec = g.ro("MATCH (a:Assertion {object_id:'system:statements', predicate:'OWNS'}) WHERE a.status = 'current' "
               "RETURN a.id AS id, a.subject_id AS s")[0]
    acts = Actions(g)
    pv = acts.confirm_preview(BOB, assertion_id=rec["id"])
    assert pv["admissible"] and pv["actor_eligible"], pv
    acts.confirm_fact(Actor(BOB, client="judge"), assertion_id=rec["id"])
    p = run_tool(Ctx(g), "get_owner", {"entity_id": "system:statements"})
    f = [x for x in p["items"][0]["facts"] if x["predicate"] == "OWNS"][0]
    assert f["subject_id"] == rec["s"] and f["open_disputes"] == []
