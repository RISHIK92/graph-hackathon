"""Phase 2 item 7: named workspace checkpoints via GRAPH.COPY on both FalkorDB versions."""
import uuid

import pytest
from starlette.testclient import TestClient

import api.accounts as acc
import api.app as api_app
import api.workspaces as ws
from brain.config import settings
from brain.db import Graph

DOC_A = b"# Billing overview\n\nBilling is part of Core Banking. Payments owns Billing.\n"
DOC_B = b"# Aurora overview\n\nAurora is part of Core Banking. Infra owns Aurora.\n"


@pytest.fixture
def env_accounts(monkeypatch):
    name = f"acct_{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("NODUS_ACCOUNTS", "on")
    monkeypatch.setenv("NODUS_ACCOUNTS_GRAPH", name)
    acc._RATE.clear()
    acc._STORE.clear()
    api_app.RATE.clear()
    made: list[str] = []
    yield made
    for w in made:
        ws.drop_checkpoints(w)
        ws.drop(w)
    acc._STORE.clear()
    Graph(name=name).delete()


def _signup(made: list[str], email: str = "rec@nodus.local"):
    c = TestClient(api_app.app)
    me = c.post("/auth/signup", json={"email": email, "password": "a long password"}).json()
    w = me["account"]["workspace"]
    made.append(w)
    c.headers["x-csrf-token"] = me["csrf"]
    return c, w


def _admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.admin_token}"}


def test_checkpoint_auth_and_prod_guard(env_accounts, monkeypatch):
    c, w = _signup(env_accounts)
    # Without admin token -> 401
    assert c.post("/admin/checkpoint", json={"name": "clean"}).status_code == 401
    assert c.post("/admin/reset", json={"checkpoint": "clean"}).status_code == 401

    # With public write token -> 401
    pub = {"Authorization": f"Bearer {settings.public_write_token}"}
    assert c.post("/admin/checkpoint", json={"name": "clean"}, headers=pub).status_code == 401
    assert c.post("/admin/reset", json={"checkpoint": "clean"}, headers=pub).status_code == 401

    # Refused when NODUS_ENV=prod unless NODUS_ALLOW_CHECKPOINTS=on
    monkeypatch.setenv("NODUS_ENV", "prod")
    monkeypatch.delenv("NODUS_ALLOW_CHECKPOINTS", raising=False)
    r1 = c.post("/admin/checkpoint", json={"name": "clean"}, headers=_admin_headers())
    assert r1.status_code == 403
    r2 = c.post("/admin/reset", json={"checkpoint": "clean"}, headers=_admin_headers())
    assert r2.status_code == 403

    # Allowed when NODUS_ALLOW_CHECKPOINTS=on
    monkeypatch.setenv("NODUS_ALLOW_CHECKPOINTS", "on")
    r3 = c.post("/admin/checkpoint", json={"name": "clean"}, headers=_admin_headers())
    assert r3.status_code == 200, r3.text
    assert r3.json() == {"workspace": w, "checkpoint": "clean", "graph": f"{w}__cp_clean"}


def test_checkpoint_save_mutate_restore_and_chat_history(env_accounts):
    c, w = _signup(env_accounts)
    # Seed initial state (clean: 1 doc, 0 chat turns)
    assert c.post("/admin/upload", params={"filename": "billing.md"}, content=DOC_A).status_code == 200
    assert c.get("/chat").json()["turns"] == []

    # Save 'clean' checkpoint
    r_clean = c.post("/admin/checkpoint", json={"name": "clean"}, headers=_admin_headers())
    assert r_clean.status_code == 200, r_clean.text
    assert r_clean.json()["graph"] == f"{w}__cp_clean"

    # Mutate workspace: add a chat turn + upload a second doc + create a snapshot graph
    sid = c.post("/sessions", json={}).json()["session_id"]
    c.post(f"/sessions/{sid}/turns/sync", json={"text": "Who owns Billing?"})
    assert len(c.get("/chat").json()["turns"]) == 1
    assert c.post("/admin/upload", params={"filename": "aurora.md"}, content=DOC_B).status_code == 200
    counts_after = c.get("/workspace").json()["counts"]
    assert counts_after["sources"] == 2

    # Save 'after-turn' checkpoint
    r_turn = c.post("/admin/checkpoint", json={"name": "after-turn"}, headers=_admin_headers())
    assert r_turn.status_code == 200

    # Create a dummy derived snapshot graph to verify restore drops snapshots and LRU entry
    snap_g = Graph(name=f"{w}__snap_now")
    snap_g.write("CREATE (:Meta {version:'v1'})")
    old_ws_obj = ws.get(w)

    # Restore 'clean' checkpoint
    r_res = c.post("/admin/reset", json={"checkpoint": "clean"}, headers=_admin_headers())
    assert r_res.status_code == 200, r_res.text
    assert r_res.json() == {"workspace": w, "checkpoint": "clean", "graph": f"{w}__cp_clean"}

    # Verify LRU entry was replaced and derived snapshot graph was dropped
    assert ws.get(w) is not old_ws_obj
    raw_graphs = [n.decode() if isinstance(n, bytes) else n for n in Graph(name=w).raw("GRAPH.LIST")]
    assert f"{w}__snap_now" not in raw_graphs
    assert f"{w}__cp_clean" in raw_graphs
    assert f"{w}__cp_after-turn" in raw_graphs

    # Verify workspace state & empty chat thread restored to 'clean'
    assert c.get("/workspace").json()["counts"]["sources"] == 1
    assert c.get("/chat").json()["turns"] == []

    # Restore 'after-turn' checkpoint using explicit workspace parameter without session cookie
    admin_only = TestClient(api_app.app)
    r_res2 = admin_only.post(
        "/admin/reset",
        json={"checkpoint": "after-turn", "workspace": w},
        headers=_admin_headers(),
    )
    assert r_res2.status_code == 200, r_res2.text
    assert c.get("/workspace").json()["counts"]["sources"] == 2
    turns = c.get("/chat").json()["turns"]
    assert len(turns) == 1 and turns[0]["text"] == "Who owns Billing?"


@pytest.mark.parametrize("port", [6391, 6392])
def test_checkpoint_graph_copy_both_falkor_versions(port):
    """Save, mutate, restore and compare directly on both FalkorDB 6.0.1 (6391) and 4.22.0 (6392)."""
    w = f"ws_test_{uuid.uuid4().hex[:8]}"
    g = Graph(name=w, port=port)
    try:
        g.write("CREATE (:Entity:System {id:'system:ledger', name:'Ledger'}), (:Source {id:'src_1', kind:'doc'})")
        ws.save_checkpoint(w, "clean", port=port)
        g.write("CREATE (:Entity:System {id:'system:aurora', name:'Aurora'}), (:Source {id:'src_2', kind:'chat_session'})")
        assert g.ro("MATCH (e:Entity) RETURN count(e) AS n")[0]["n"] == 2

        ws.restore_checkpoint(w, "clean", port=port)
        g2 = Graph(name=w, port=port)
        rows = g2.ro("MATCH (e:Entity) RETURN e.id AS id")
        assert rows == [{"id": "system:ledger"}]
        srcs = g2.ro("MATCH (s:Source) RETURN s.id AS id")
        assert srcs == [{"id": "src_1"}]
    finally:
        ws.drop_checkpoints(w, port=port)
        Graph(name=w, port=port).delete()
