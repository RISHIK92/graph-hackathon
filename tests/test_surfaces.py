"""Surface-read tests: overview, directory, names, entity panels, graph, neighbourhood, edges, spans, sources, people, and pending."""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

import api.app as api_app
from api.agent import Agent
from brain.actions import Actions, Actor
from brain.config import settings

from .test_actions import _fact, world  # noqa: F401


@pytest.fixture
def surface_client(world):
    old_g = api_app.G
    old_agent = api_app.AGENT
    old_anon = dict(api_app.ANON)
    api_app.G = world["g"]
    api_app.AGENT = Agent(world["g"], world["clock"])
    api_app.ANON.clear()
    client = TestClient(api_app.app)
    try:
        yield client, world
    finally:
        api_app.G = old_g
        api_app.AGENT = old_agent
        api_app.ANON.clear()
        api_app.ANON.update(old_anon)


# 1. Overview

def test_overview_endpoint(surface_client):
    client, world = surface_client
    r = client.get("/overview")
    assert r.status_code == 200
    data = r.json()
    assert "as_of" in data
    assert "teams" in data
    assert "decisions" in data
    assert "pending" in data

    # Payments team check
    payments = next((t for t in data["teams"] if t["id"] == "team:payments"), None)
    assert payments is not None
    assert any(lead["id"] == "person:priya" for lead in payments["leads"])
    assert any(owned["id"] == "system:ledger" for owned in payments["owns"])


def test_overview_temporal_as_of_and_dispute(surface_client):
    client, world = surface_client
    wp = world["wp"]

    # At as_of=1, Ledger is not owned yet (valid_from=2)
    r_past = client.get("/overview?as_of=1")
    assert r_past.status_code == 200
    p_past = next((t for t in r_past.json()["teams"] if t["id"] == "team:payments"), None)
    assert not any(owned["id"] == "system:ledger" for owned in p_past["owns"])

    # Create open dispute on Payments owning Ledger
    _fact(wp, "OWNS", "team:infra", "system:ledger", 3, "sp6", form="chat")

    r_now = client.get("/overview")
    p_now = next((t for t in r_now.json()["teams"] if t["id"] == "team:payments"), None)
    ledger_owned = next((o for o in p_now["owns"] if o["id"] == "system:ledger"), None)
    assert ledger_owned is not None
    assert ledger_owned["disputed"] is True


# 2. Directory

def test_directory_endpoint(surface_client):
    client, _ = surface_client
    r = client.get("/directory")
    assert r.status_code == 200
    data = r.json()
    assert "as_of" in data
    for key in ("teams", "systems", "projects", "people", "decisions", "tickets"):
        assert key in data

    # Systems
    ledger = next((s for s in data["systems"] if s["id"] == "system:ledger"), None)
    assert ledger is not None
    assert ledger["owner"]["id"] == "team:payments"

    # People
    priya = next((p for p in data["people"] if p["id"] == "person:priya"), None)
    assert priya is not None
    assert any(team["id"] == "team:payments" for team in priya["leads"])

    # Tickets
    rds42 = next((k for k in data["tickets"] if k["id"] == "ticket:rds-42"), None)
    assert rds42 is not None
    assert rds42["about"]["id"] == "system:ledger"
    assert rds42["state"] == "open"


# 3. Names

def test_names_endpoint(surface_client):
    client, _ = surface_client
    # Empty query returns empty dict
    assert client.get("/names").json() == {}
    assert client.get("/names?ids=").json() == {}

    # Full and bare IDs
    r = client.get("/names?ids=system:ledger,priya")
    assert r.status_code == 200
    data = r.json()
    assert "system:ledger" in data
    assert data["system:ledger"]["name"] == "Ledger"
    assert data["system:ledger"]["label"] == "System"
    assert "ledger" in data

    assert "person:priya" in data
    assert data["person:priya"]["name"] == "Priya Raman"
    assert "priya" in data


# 4. Entity Panels

def test_entity_panel_system(surface_client):
    client, _ = surface_client
    r = client.get("/entities/system:ledger")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "system:ledger"
    assert data["name"] == "Ledger"
    assert "owner" in data
    assert "depends_on" in data
    assert "depended_on_by" in data
    assert "decisions" in data
    assert "history" in data
    assert "OWNS" in data["history"]
    assert "sources" in data


def test_entity_panel_team(surface_client):
    client, _ = surface_client
    r = client.get("/entities/team:payments")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "team:payments"
    assert data["name"] == "Payments"
    assert "lead" in data
    assert any(lead["id"] == "person:priya" for lead in data["lead"])
    assert "history" in data
    assert "LEADS" in data["history"]


def test_entity_panel_not_found(surface_client):
    client, _ = surface_client
    r = client.get("/entities/system:nonexistent")
    assert r.status_code == 404


def test_entity_history_endpoint(surface_client):
    client, _ = surface_client
    r = client.get("/entities/system:ledger/history?predicate=OWNS")
    assert r.status_code == 200
    data = r.json()
    assert data["tool"] == "get_history"
    assert len(data["items"]) > 0


# 5. Graph & Neighbourhood

def test_graph_endpoint_and_filters(surface_client):
    client, _ = surface_client
    r = client.get("/graph")
    assert r.status_code == 200
    data = r.json()
    assert "nodes" in data
    assert "edges" in data
    assert "disputed" in data
    assert "stale" in data
    assert "ticks" in data
    assert len(data["nodes"]) > 0
    assert len(data["edges"]) > 0

    # Labels filter
    r_filtered = client.get("/graph?labels=System,Team")
    assert r_filtered.status_code == 200
    nodes_filtered = r_filtered.json()["nodes"]
    assert all(any(lbl in ("System", "Team") for lbl in n["labels"]) for n in nodes_filtered)


def test_graph_neighbourhood(surface_client):
    client, _ = surface_client
    r = client.get("/graph/neighbourhood?ids=system:ledger&hops=1")
    assert r.status_code == 200
    data = r.json()
    assert "nodes" in data
    assert "edges" in data
    node_ids = {n["id"] for n in data["nodes"]}
    assert "system:ledger" in node_ids


# 6. Edges, Spans & Sources

def test_edge_endpoint(surface_client):
    client, world = surface_client
    aid = world["ids"]["own_p"]
    r = client.get(f"/edges/{aid}")
    assert r.status_code == 200
    data = r.json()
    assert data["aid"] == aid
    assert len(data["facts"]) > 0
    assert len(data["spans"]) > 0


def test_spans_endpoint(surface_client):
    client, _ = surface_client
    r = client.get("/spans/sp0")
    assert r.status_code == 200
    data = r.json()
    assert data["text"] == "roster priya"
    assert data["kind"] == "wiki"
    assert "revisions" in data

    # Unknown span -> 404
    assert client.get("/spans/sp_nonexistent").status_code == 404


def test_sources_endpoint_and_draft_banner(surface_client):
    client, world = surface_client
    g, clock = world["g"], world["clock"]

    r = client.get("/sources/src:test")
    assert r.status_code == 200
    data = r.json()
    assert data["source"]["id"] == "src:test"
    assert len(data["spans"]) > 0
    assert "roster priya" in data["text"]

    # Unknown source -> 404
    assert client.get("/sources/src_nonexistent").status_code == 404

    # Draft source has banner
    acts = Actions(g, clock)
    act = acts.route_to_owner(Actor("person:eve"), "ticket:rds-42")
    draft_src_id = g.ro("MATCH (:Action {id:$id})-[:PRODUCED]->(s:Source {kind:'draft'}) RETURN s.id AS id",
                        {"id": act["action_id"]})[0]["id"]
    r_draft = client.get(f"/sources/{draft_src_id}")
    assert r_draft.status_code == 200
    assert "banner" in r_draft.json()
    assert "agent draft: not evidence" in r_draft.json()["banner"]

    # When action is undone, banner adds '· withdrawn'
    acts.undo_action(Actor("person:eve"), act["action_id"])
    r_undone_draft = client.get(f"/sources/{draft_src_id}")
    assert r_undone_draft.status_code == 200
    assert "withdrawn" in r_undone_draft.json()["banner"]


# 7. Paths

def test_paths_endpoint_from_turn_pack_cache(surface_client):
    client, _ = surface_client
    s = client.post("/sessions", headers={"Authorization": f"Bearer {settings.public_write_token}"},
                    json={"acting_as": "person:priya"}).json()
    sid = s["session_id"]
    client.post(f"/sessions/{sid}/turns/sync", headers={"Authorization": f"Bearer {settings.public_write_token}"},
                json={"text": "Who owns Ledger?"})

    path_id = None
    for t in api_app.AGENT.turn_log.values():
        for p in t.get("packs", {}).values():
            for it in p.get("items", []):
                if it.get("path"):
                    path_id = it["path"]["path_id"]
                    break

    assert path_id is not None
    r_path = client.get(f"/paths/{path_id}")
    assert r_path.status_code == 200
    assert r_path.json()["path_id"] == path_id
    assert len(r_path.json()["steps"]) > 0

    assert client.get("/paths/pa_missing").status_code == 404


# 8. People & Pending

def test_people_endpoint(surface_client):
    client, _ = surface_client
    r = client.get("/people")
    assert r.status_code == 200
    ppl = r.json()
    assert len(ppl) >= 3
    priya = next((p for p in ppl if p["id"] == "person:priya"), None)
    assert priya is not None
    assert "Payments" in priya["leads"]


def test_people_pending_endpoint(surface_client):
    client, world = surface_client
    g, clock = world["g"], world["clock"]

    # Eve routes ticket
    acts = Actions(g, clock)
    act = acts.route_to_owner(Actor("person:eve"), "ticket:rds-42")

    # Priya has it awaiting confirmation
    r_priya = client.get("/people/person:priya/pending")
    assert r_priya.status_code == 200
    data_priya = r_priya.json()
    assert "awaiting" in data_priya
    assert "mine" in data_priya
    assert "log" in data_priya
    assert any(item["action_id"] == act["action_id"] for item in data_priya["awaiting"])

    # Eve has it in 'mine'
    r_eve = client.get("/people/person:eve/pending")
    assert r_eve.status_code == 200
    data_eve = r_eve.json()
    assert any(item["action_id"] == act["action_id"] for item in data_eve["mine"])
    assert any(log_item["id"] == act["action_id"] for log_item in data_eve["log"])
