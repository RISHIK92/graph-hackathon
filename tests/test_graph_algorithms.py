"""Item 17: graph algorithms on snapshot graphs. Snapshot liveness and invalidation, each tool's ranks or sets
on both versions (never raw scores, F25), path de-duplication, and agent routing for the four question types."""
from api.agent import Agent, heuristic_plan
from brain import snapshot, store
from brain.tools import Ctx, run_tool

from .conftest import make_span
from .test_actions import _fact, world  # noqa: F401
from .test_agent import _counting_world, answer_of, run

JAN, FEB, MAR, JUN = 1767225600000, 1769904000000, 1772323200000, 1780000000000


def _vault(world):
    """Platform owned Vault from 1 Jan 2026, Payments from 1 Mar 2026; the clock is in June."""
    g, wp, clock = world["g"], world["wp"], world["clock"]
    clock.t = JUN
    store.upsert_entities(g, [{"id": "system:vault", "name": "Vault", "aliases": []}])
    make_span(g, "sp_v1", "platform owns vault", 1)
    make_span(g, "sp_v2", "payments owns vault", 1)
    _fact(wp, "OWNS", "team:platform", "system:vault", JAN, "sp_v1")
    _fact(wp, "OWNS", "team:payments", "system:vault", MAR, "sp_v2")
    clock.tick(10)


def _owns(g, as_of=None, now=None):
    snap = snapshot.snapshot(g, as_of, now)
    return {(r["owner"], r["id"]) for r in snap.q("snap_owns")}


def test_snapshot_holds_the_edges_live_at_its_date(world):
    g = world["g"]
    _vault(world)
    now = _owns(g, now=world["clock"]())
    assert ("team:payments", "system:vault") in now and ("team:platform", "system:vault") not in now
    then = _owns(g, as_of=FEB)
    assert ("team:platform", "system:vault") in then and ("team:payments", "system:vault") not in then
    assert snapshot.name_for(g, FEB).endswith("__snap_20260201")


def test_snapshot_is_rebuilt_after_a_write(world):
    g, wp, clock = world["g"], world["wp"], world["clock"]
    before = _owns(g, now=clock())
    assert ("team:infra", "system:ledger") not in before
    make_span(g, "sp_new", "infra owns statements", 1)
    store.upsert_entities(g, [{"id": "system:statements", "name": "Statements", "aliases": []}])
    _fact(wp, "OWNS", "team:infra", "system:statements", 3, "sp_new")
    clock.tick()
    assert ("team:infra", "system:statements") in _owns(g, now=clock())


def test_critical_systems_ranks_the_most_depended_on(world):
    _counting_world(world)
    pack = run_tool(Ctx(world["g"], now=world["clock"]()), "critical_systems", {"k": 3})
    ranks = [(it["ranking"]["rank"], it["ranking"]["name"]) for it in pack["items"] if it.get("ranking")]
    assert ranks[0] == (1, "Ledger") and ranks[1] == (2, "Checkout")
    ledger = next(it for it in pack["items"] if (it.get("ranking") or {}).get("name") == "Ledger")
    assert {f["predicate"] for f in ledger["facts"]} == {"DEPENDS_ON"} and ledger["spans"]
    assert "PageRank" in pack["args"]["method"]


def test_connection_between_dedupes_paths_and_cites_each_edge(world, monkeypatch):
    g, clock = world["g"], world["clock"]
    ctx = Ctx(g, now=clock())
    pack = run_tool(ctx, "connection_between", {"from_id": "person:priya", "to_id": "system:ledger"})
    paths = [tuple(s["node"]["id"] for s in it["path"]["steps"]) for it in pack["items"] if it.get("path")]
    assert paths == [("person:priya", "team:payments", "system:ledger")]
    steps = pack["items"][0]["path"]["steps"]
    assert [(s["edge"]["type"], s["edge"]["dir"]) for s in steps[1:]] == [("LEADS", "forward"), ("OWNS", "forward")]
    real = Ctx.q

    def doubled(self, name, params, timeout=2000):
        rows = real(self, name, params, timeout)
        return rows + rows if name == "snap_paths" else rows
    monkeypatch.setattr(Ctx, "q", doubled)
    again = run_tool(Ctx(g, now=clock()), "connection_between", {"from_id": "person:priya", "to_id": "system:ledger"})
    assert len([it for it in again["items"] if it.get("path")]) == 1


def test_key_people_ranks_the_connectors(world):
    _counting_world(world)
    pack = run_tool(Ctx(world["g"], now=world["clock"]()), "key_people", {"k": 3})
    ranked = [it["ranking"] for it in pack["items"] if it.get("ranking")]
    # Bob leads Infra and is a member of Payments: the only person between two teams. Both of Priya's edges
    # go to Payments, so nothing runs through her.
    assert ranked and ranked[0]["name"] == "Bob Okafor" and ranked[0]["rank"] == 1
    assert all(it["facts"] for it in pack["items"])


def test_knowledge_gaps_lists_ownerless_systems_and_leaderless_teams(world):
    g, wp, clock = world["g"], world["wp"], world["clock"]
    store.upsert_entities(g, [{"id": "system:orphan", "name": "Orphan", "aliases": []},
                              {"id": "team:nolead", "name": "Nolead", "aliases": []}])
    make_span(g, "sp_nl", "nolead owns orphan", 1)
    _fact(wp, "OWNS", "team:nolead", "system:orphan", 1, "sp_nl")
    clock.tick()
    pack = run_tool(Ctx(g, now=clock()), "knowledge_gaps", {})
    agg = [it["aggregate"] for it in pack["items"]]
    systems = next(a for a in agg if "system" in a["text"])
    teams = next(a for a in agg if "team" in a["text"])
    assert {m["name"] for m in systems["members"]} >= {"Orphan"} and "Ledger" not in {m["name"] for m in systems["members"]}
    assert "Nolead" in {m["name"] for m in teams["members"]}


def test_agent_routes_the_four_question_types(world):
    _counting_world(world)
    for q, intent in (("Which systems are most critical?", "critical"), ("How is Bob Okafor connected to Ledger?", "path"),
                      ("Who are our single points of failure?", "key_people"), ("Where are our knowledge gaps?", "gaps")):
        assert heuristic_plan(q)["intent"] == intent, q
    agent = Agent(world["g"], world["clock"])
    s = agent.create_session("judge", "person:eve")
    for q, tool in (("Which systems are most critical?", "critical_systems"),
                    ("How is Bob Okafor connected to Ledger?", "connection_between"),
                    ("Who are our single points of failure?", "key_people"), ("Where are our knowledge gaps?", "knowledge_gaps")):
        ev = run(agent, s, q)
        assert tool in [e["name"] for e in ev if e["event"] == "tool_call"], q
        ans = answer_of(ev)
        assert not ans["abstained"], q
    lead = answer_of(run(agent, s, "Which systems are most critical?"))["assembled"]["lead"]
    assert lead.startswith("Most depended-on systems now: 1. Ledger, 2. Checkout"), lead


def test_reset_drops_snapshot_graphs(world):
    """/admin/reset and `brain reset` rebuild the main graph; its derived snapshots go with it."""
    from brain.cli import reset_seed
    g = world["g"]
    snapshot.snapshot(g, None, world["clock"]())
    assert snapshot.snapshots(g)
    reset_seed(g, "world/seeds/1")
    assert not snapshot.snapshots(g)
