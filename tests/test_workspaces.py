"""Item 24 step 2: one FalkorDB graph per workspace. Two accounts never see each other's data, the schema is
set up on each new graph (F23), the owner can upload into and reset their own workspace, and the MCP server
reads the workspace its API key names."""
import uuid

import pytest
from starlette.testclient import TestClient

import api.accounts as acc
import api.app as api_app
import api.workspaces as ws
from brain.db import Graph

DOC = b"# Billing overview\n\nBilling is part of Core Banking. Payments owns Billing.\n"


@pytest.fixture
def accounts_on(monkeypatch):
    name = f"acct_{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("NODUS_ACCOUNTS", "on")
    monkeypatch.setenv("NODUS_ACCOUNTS_GRAPH", name)
    acc._RATE.clear()
    acc._STORE.clear()
    made: list[str] = []
    yield made
    for w in made:
        ws.drop(w)
    acc._STORE.clear()
    Graph(name=name).delete()


def _user(made, email):
    c = TestClient(api_app.app)
    me = c.post("/auth/signup", json={"email": email, "password": "a long password"}).json()
    made.append(me["account"]["workspace"])
    c.headers["x-csrf-token"] = me["csrf"]
    return c, me["account"]["workspace"]


def test_a_new_workspace_is_an_empty_graph_with_the_schema(accounts_on):
    c, name = _user(accounts_on, "a@example.com")
    st = c.get("/workspace").json()
    assert st["workspace"] == name and st["empty"] and st["counts"]["sources"] == 0
    g = Graph(name=name)
    assert g.ro("MATCH (s:GuardFail {id:'sentinel'}) RETURN count(s) AS n")[0]["n"] == 1
    assert {r["label"] for r in g.ro("CALL db.constraints() YIELD label RETURN label")} >= {"Assertion", "Span", "Source"}


def test_two_workspaces_never_see_each_others_data(accounts_on):
    a, wa = _user(accounts_on, "a@example.com")
    b, wb = _user(accounts_on, "b@example.com")
    assert wa != wb
    r = a.post("/admin/upload", params={"filename": "billing.md"}, content=DOC)
    assert r.status_code == 200, r.text
    assert r.json()["sources"] >= 1
    assert not a.get("/workspace").json()["empty"] and b.get("/workspace").json()["empty"]
    span = Graph(name=wa).ro("MATCH (s:Span) RETURN s.id AS id LIMIT 1")[0]["id"]
    assert a.get(f"/spans/{span}").status_code == 200 and b.get(f"/spans/{span}").status_code == 404
    sid = b.post("/sessions", json={}).json()["session_id"]
    ev = b.post(f"/sessions/{sid}/turns/sync", json={"text": "Who owns Billing?"}).json()["events"]
    ans = next(e for e in ev if e["event"] == "answer")
    assert ans["abstained"] or "Payments" not in str(ans["assembled"])


def test_the_owner_resets_their_workspace_to_empty(accounts_on):
    a, name = _user(accounts_on, "a@example.com")
    a.post("/admin/upload", params={"filename": "billing.md"}, content=DOC)
    assert not a.get("/workspace").json()["empty"]
    assert a.post("/workspace/reset").status_code == 200
    assert a.get("/workspace").json()["empty"]
    assert Graph(name=name).ro("MATCH (s:GuardFail {id:'sentinel'}) RETURN count(s) AS n")[0]["n"] == 1


def test_a_workspace_has_a_source_limit(accounts_on, monkeypatch):
    monkeypatch.setenv("NODUS_WS_MAX_SOURCES", "1")
    a, _ = _user(accounts_on, "a@example.com")
    assert a.post("/admin/upload", params={"filename": "one.md"}, content=DOC).status_code == 200
    r = a.post("/admin/upload", params={"filename": "two.md"}, content=b"# Two\n\nInfra owns Aurora.\n")
    assert r.status_code == 413 and "limit" in r.text


def test_logged_out_requests_have_no_workspace(accounts_on):
    c = TestClient(api_app.app)
    assert c.get("/workspace").status_code == 401
    assert c.post("/workspace/reset").status_code == 401
    assert ws.current() is None


def test_the_mcp_server_reads_the_workspace_its_key_names(accounts_on):
    a, name = _user(accounts_on, "a@example.com")
    key = a.post("/auth/keys").json()["key"]
    from mcp_server import server as mcp
    g = mcp.graph_for_key(key)
    assert g is not None and g.name == name
    assert mcp.graph_for_key("nodus_not_a_key") is None


def test_the_nightly_job_empties_the_shared_demo_workspace(accounts_on, monkeypatch):
    monkeypatch.setenv("NODUS_DEMO_EMAIL", "demo@nodus.test")
    monkeypatch.setenv("NODUS_DEMO_PASSWORD", "demo password 1")
    c = TestClient(api_app.app)
    me = c.post("/auth/demo").json()
    accounts_on.append(me["account"]["workspace"])
    c.headers["x-csrf-token"] = me["csrf"]
    c.post("/admin/upload", params={"filename": "billing.md"}, content=DOC)
    assert not c.get("/workspace").json()["empty"]
    assert api_app.empty_demo_workspace() == me["account"]["workspace"]
    assert c.get("/workspace").json()["empty"]
