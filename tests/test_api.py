"""API endpoint tests: auth behavior, sessions, turns, confirm/undo, and write restrictions."""
from __future__ import annotations


import pytest
from starlette.testclient import TestClient

import api.app as api_app
from api.agent import Agent
from brain.actions import Actions, Actor
from brain.config import settings

from .conftest import make_span
from .test_actions import _fact, world  # noqa: F401


@pytest.fixture
def api_client(world):
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


# 1. Health

def test_health_endpoint(api_client):
    client, world = api_client
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["reachable"] is True
    assert data["pin_ok"] == (world["g"].module_version() == settings.pin)
    assert "past_belief_engine" in data
    assert data["constraints_operational"] is True


# 2. Admin auth gating

def test_admin_integrity_requires_admin_token(api_client):
    client, _ = api_client
    # No auth header -> 401
    r_no_auth = client.get("/admin/integrity")
    assert r_no_auth.status_code == 401
    assert "admin token required" in r_no_auth.json()["detail"]

    # Wrong token -> 401
    r_wrong = client.get("/admin/integrity", headers={"Authorization": "Bearer bad-token"})
    assert r_wrong.status_code == 401

    # Public write token (not admin) -> 401
    r_public = client.get("/admin/integrity", headers={"Authorization": f"Bearer {settings.public_write_token}"})
    assert r_public.status_code == 401

    # Admin token -> 200
    r_admin = client.get("/admin/integrity", headers={"Authorization": f"Bearer {settings.admin_token}"})
    assert r_admin.status_code == 200
    data = r_admin.json()
    assert data["ok"] is True
    assert data["violations"] == []

    # Deep check works too
    r_deep = client.get("/admin/integrity?deep=true", headers={"Authorization": f"Bearer {settings.admin_token}"})
    assert r_deep.status_code == 200
    assert r_deep.json()["ok"] is True


def test_admin_rebuild_projections_requires_admin_token(api_client):
    client, _ = api_client
    # No auth -> 401
    r_no_auth = client.post("/admin/rebuild-projections")
    assert r_no_auth.status_code == 401

    # Public token -> 401
    r_public = client.post("/admin/rebuild-projections", headers={"Authorization": f"Bearer {settings.public_write_token}"})
    assert r_public.status_code == 401

    # Admin token -> 200
    r_admin = client.post("/admin/rebuild-projections", headers={"Authorization": f"Bearer {settings.admin_token}"})
    assert r_admin.status_code == 200
    assert "chains" in r_admin.json()


def test_admin_reset_requires_admin_token(api_client):
    client, _ = api_client
    r_no_auth = client.post("/admin/reset")
    assert r_no_auth.status_code == 401

    r_public = client.post("/admin/reset", headers={"Authorization": f"Bearer {settings.public_write_token}"})
    assert r_public.status_code == 401


def test_admin_ingest_requires_admin_token(api_client):
    client, _ = api_client
    r_no_auth = client.post("/admin/ingest", json={"render_dir": "/tmp/dummy"})
    assert r_no_auth.status_code == 401

    r_public = client.post("/admin/ingest", headers={"Authorization": f"Bearer {settings.public_write_token}"},
                           json={"render_dir": "/tmp/dummy"})
    assert r_public.status_code == 401


# 3. Session creation & access control

def test_session_creation_anonymous_vs_authenticated(api_client):
    client, _ = api_client
    # Anonymous session (no token)
    r_anon = client.post("/sessions", json={"acting_as": "person:eve"})
    assert r_anon.status_code == 200
    anon_data = r_anon.json()
    assert anon_data["anonymous"] is True
    assert anon_data["acting_as"] == "person:eve"
    assert anon_data["session_id"].startswith("anon_")

    # Authenticated session with public write token
    r_auth = client.post("/sessions", headers={"Authorization": f"Bearer {settings.public_write_token}"},
                         json={"acting_as": "person:priya"})
    assert r_auth.status_code == 200
    auth_data = r_auth.json()
    assert auth_data["anonymous"] is False
    assert auth_data["acting_as"] == "person:priya"
    assert not auth_data["session_id"].startswith("anon_")


def test_session_acting_as_update(api_client):
    client, _ = api_client
    r = client.post("/sessions", json={"acting_as": "person:eve"})
    sid = r.json()["session_id"]

    r_upd = client.put(f"/sessions/{sid}/acting-as", json={"person_id": "person:bob"})
    assert r_upd.status_code == 200
    assert r_upd.json()["acting_as"] == "person:bob"


def test_authenticated_session_cross_client_forbidden(api_client):
    client, _ = api_client
    # Create an authenticated session
    r_auth = client.post("/sessions", headers={"Authorization": f"Bearer {settings.public_write_token}"},
                         json={"acting_as": "person:priya"})
    sid = r_auth.json()["session_id"]

    # Trying to access that authenticated session anonymously -> 403
    r_turn = client.post(f"/sessions/{sid}/turns/sync", json={"text": "Who owns Ledger?"})
    assert r_turn.status_code == 403
    assert "session does not belong to this client" in r_turn.json()["detail"]


# 4. Agent write restrictions in chat turns

def test_anonymous_turn_read_allowed_but_writes_restricted(api_client):
    client, world = api_client
    g = world["g"]
    before_nodes = g.ro("MATCH (n) RETURN count(n) AS n")[0]["n"]

    r_anon = client.post("/sessions", json={"acting_as": "person:eve"})
    sid = r_anon.json()["session_id"]

    # Read turn succeeds
    r_read = client.post(f"/sessions/{sid}/turns/sync", json={"text": "Who owns Ledger?"})
    assert r_read.status_code == 200
    events = r_read.json()["events"]
    ans = next(e for e in events if e["event"] == "answer")
    assert not ans["abstained"]
    assert any("Payments owns Ledger" in line["text"] for line in ans["assembled"]["lines"])

    # Anonymous user asking for a write: agent refuses and marks status 'needs_token'
    r_write = client.post(f"/sessions/{sid}/turns/sync", json={"text": "Route RDS-42 to the owner"})
    assert r_write.status_code == 200
    ev_write = r_write.json()["events"]
    act = next((e for e in ev_write if e["event"] == "action"), None)
    assert act is not None
    assert act["status"] == "needs_token"

    # Graph remains completely unchanged
    after_nodes = g.ro("MATCH (n) RETURN count(n) AS n")[0]["n"]
    assert after_nodes == before_nodes


def test_authenticated_turn_and_trace(api_client):
    client, _ = api_client
    r_auth = client.post("/sessions", headers={"Authorization": f"Bearer {settings.public_write_token}"},
                         json={"acting_as": "person:priya"})
    sid = r_auth.json()["session_id"]

    r_turn = client.post(f"/sessions/{sid}/turns/sync",
                         headers={"Authorization": f"Bearer {settings.public_write_token}"},
                         json={"text": "Who owns Ledger?"})
    assert r_turn.status_code == 200
    events = r_turn.json()["events"]
    ans = next(e for e in events if e["event"] == "answer")
    turn_id = ans["turn_id"]

    # Trace endpoint returns full turn trace
    r_trace = client.get(f"/turns/{turn_id}/trace")
    assert r_trace.status_code == 200
    trace = r_trace.json()
    assert trace["turn_id"] == turn_id
    assert "queries" in trace
    assert "packs" in trace

    # Unknown turn trace -> 404
    r_404 = client.get("/turns/turn_nonexistent/trace")
    assert r_404.status_code == 404


# 5. Direct confirm and undo endpoints

def test_confirm_requires_token(api_client):
    client, world = api_client
    g, clock = world["g"], world["clock"]

    # Eve routes ticket
    acts = Actions(g, clock)
    act_res = acts.route_to_owner(Actor("person:eve"), "ticket:rds-42")
    aid = act_res["action_id"]

    # Anonymous session cannot confirm -> 401
    r_anon = client.post("/sessions", json={"acting_as": "person:priya"})
    sid_anon = r_anon.json()["session_id"]
    r_no_tok = client.post(f"/actions/{aid}/confirm", json={"session_id": sid_anon, "request_id": "req-1"})
    assert r_no_tok.status_code == 401
    assert "writes need the judges' token" in r_no_tok.json()["detail"]


def test_confirm_and_undo_lifecycle_with_server_side_actor(api_client):
    client, world = api_client
    g, clock = world["g"], world["clock"]

    # Eve routes ticket
    acts = Actions(g, clock)
    act_res = acts.route_to_owner(Actor("person:eve"), "ticket:rds-42")
    route_aid = act_res["action_id"]

    # Session 1: Priya (eligible lead)
    s_priya = client.post("/sessions", headers={"Authorization": f"Bearer {settings.public_write_token}"},
                          json={"acting_as": "person:priya"}).json()
    sid_priya = s_priya["session_id"]

    # Session 2: Bob (ineligible lead)
    s_bob = client.post("/sessions", headers={"Authorization": f"Bearer {settings.public_write_token}"},
                        json={"acting_as": "person:bob"}).json()
    sid_bob = s_bob["session_id"]

    # Check confirmers preview for Bob -> actor_eligible is False
    r_prev_bob = client.get(f"/actions/{route_aid}/confirmers?session_id={sid_bob}",
                            headers={"Authorization": f"Bearer {settings.public_write_token}"})
    assert r_prev_bob.status_code == 200
    assert r_prev_bob.json()["actor_eligible"] is False

    # Bob attempts to confirm -> refused
    r_conf_bob = client.post(f"/actions/{route_aid}/confirm",
                             headers={"Authorization": f"Bearer {settings.public_write_token}"},
                             json={"session_id": sid_bob, "request_id": "req-bob"})
    assert r_conf_bob.status_code == 200
    assert r_conf_bob.json().get("refusal", {}).get("refused") is True

    # Priya attempts to confirm -> succeeds (server-side actor is Priya)
    r_conf_priya = client.post(f"/actions/{route_aid}/confirm",
                               headers={"Authorization": f"Bearer {settings.public_write_token}"},
                               json={"session_id": sid_priya, "request_id": "req-priya"})
    assert r_conf_priya.status_code == 200
    conf_aid = r_conf_priya.json()["action_id"]
    assert conf_aid.startswith("ac_")

    # Bob cannot undo Priya's confirmation -> refused
    r_undo_bob = client.post(f"/actions/{conf_aid}/undo",
                             headers={"Authorization": f"Bearer {settings.public_write_token}"},
                             json={"session_id": sid_bob, "request_id": "req-undo-bob"})
    assert r_undo_bob.status_code == 200
    assert r_undo_bob.json().get("refusal", {}).get("refused") is True

    # Priya undoes her confirmation -> succeeds
    r_undo_priya = client.post(f"/actions/{conf_aid}/undo",
                               headers={"Authorization": f"Bearer {settings.public_write_token}"},
                               json={"session_id": sid_priya, "request_id": "req-undo-priya"})
    assert r_undo_priya.status_code == 200
    assert r_undo_priya.json()["action_id"].startswith("ac_")


def test_assertion_confirm_endpoint(api_client):
    client, world = api_client
    wp = world["wp"]

    # Create a disputed fact
    ch = _fact(wp, "OWNS", "team:infra", "system:ledger", 3, "sp6", form="chat")

    s_priya = client.post("/sessions", headers={"Authorization": f"Bearer {settings.public_write_token}"},
                          json={"acting_as": "person:priya"}).json()
    sid_priya = s_priya["session_id"]

    # Preview assertion confirmation
    r_prev = client.get(f"/assertions/{ch}/confirmers?session_id={sid_priya}",
                        headers={"Authorization": f"Bearer {settings.public_write_token}"})
    assert r_prev.status_code == 200
    assert r_prev.json()["admissible"] is True
    assert r_prev.json()["actor_eligible"] is True

    # Confirm assertion as Priya
    r_conf = client.post(f"/assertions/{ch}/confirm",
                         headers={"Authorization": f"Bearer {settings.public_write_token}"},
                         json={"session_id": sid_priya, "request_id": "req-conf-a"})
    assert r_conf.status_code == 200
    assert r_conf.json()["action_id"].startswith("ac_")


def test_admin_upload_requires_admin_token_and_a_known_format(api_client):
    client, world = api_client
    body = b"# Runbook\n\nPayments owns Ledger."
    assert client.post("/admin/upload?filename=runbook.md", content=body).status_code == 401
    admin = {"Authorization": f"Bearer {settings.admin_token}"}
    r = client.post("/admin/upload?filename=runbook.md", content=body, headers=admin)
    assert r.status_code == 200 and r.json()["sources"]
    assert client.post("/admin/upload?filename=deck.pdf", content=b"%PDF", headers=admin).status_code == 400


def test_pending_count_matches_inbox(api_client):
    """The nav badge reads one number: what this person can settle now (the Inbox's awaiting list)."""
    client, world = api_client
    assert client.get("/people/person:priya/pending/count").json() == {"awaiting": 0}
    Actions(world["g"], world["clock"]).route_to_owner(Actor("person:eve"), "ticket:rds-42")
    full = client.get("/people/person:priya/pending").json()
    assert len(full["awaiting"]) == 1
    assert client.get("/people/person:priya/pending/count").json() == {"awaiting": 1}
    assert client.get("/people/person:bob/pending/count").json() == {"awaiting": 0}


def test_pending_dispute_shows_both_sides(api_client):
    """M18: an Inbox dispute row names the recorded side and the challenger, not just the challenger."""
    client, world = api_client
    g, clock = world["g"], world["clock"]
    make_span(g, "turn3", "Infra owns Ledger", clock(), src="sess1", kind="chat_session", role="user")
    Actions(g, clock).learn_fact(Actor("person:eve"), "turn3", {"predicate": "OWNS", "subject_id": "team:infra",
                                                                "object_id": "system:ledger"}, "sess1")
    clock.tick()
    rows = [a for a in client.get("/people/person:priya/pending").json()["awaiting"] if a["type"] == "dispute"]
    assert [(a["recorded"], a["challenger"]) for a in rows] == [("Payments owns Ledger", "Infra owns Ledger")]
    assert rows[0]["summary"] == "Payments owns Ledger (recorded) vs Infra owns Ledger (challenger)"


def test_graph_hides_decisions_not_made_yet(api_client):
    """M10: at an earlier date the graph doesn't draw a decision that was only made later."""
    client, world = api_client
    from brain import store
    store.upsert_entities(world["g"], [{"id": "decision:adr-050", "name": "ADR-050", "aliases": [], "decided_at": 500}])
    assert "decision:adr-050" in {n["id"] for n in client.get("/graph").json()["nodes"]}
    assert "decision:adr-050" not in {n["id"] for n in client.get("/graph?as_of=400").json()["nodes"]}


def test_person_panel_has_a_profile(api_client):
    """m24: a person's panel says what they lead, what their teams own and what they decide."""
    client, world = api_client
    r = client.get("/entities/person:priya").json()
    prof = r["profile"]
    assert [x["name"] for x in prof["leads"]] == ["Payments"]
    assert [x["name"] for x in prof["owns_via_team"]] == ["Ledger"]
    assert prof["decides"] == []


def test_gaps_endpoint_lists_cited_knowledge_gaps(api_client):
    """Item 20: the Overview "Knowledge gaps" box reads one GET; each gap cites what it counts."""
    client, world = api_client
    from brain import store
    g, wp = world["g"], world["wp"]
    store.upsert_entities(g, [{"id": "system:orphan", "name": "Orphan", "aliases": []},
                              {"id": "team:nolead", "name": "Nolead", "aliases": []}])
    make_span(g, "sp_nl", "nolead owns orphan", 1)
    _fact(wp, "OWNS", "team:nolead", "system:orphan", 1, "sp_nl")
    resp = client.get("/gaps")
    assert resp.status_code == 200
    pack = resp.json()
    assert pack["tool"] == "knowledge_gaps"
    systems = next(it for it in pack["items"] if "system" in it["aggregate"]["text"])
    assert "Orphan" in {m["name"] for m in systems["aggregate"]["members"]} and systems["facts"]
    assert client.get("/gaps", params={"as_of": 1}).status_code == 200
