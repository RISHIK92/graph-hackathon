"""Item 24 step 3: an empty workspace's two paths. "Load the demo company" copies a template graph with
GRAPH.COPY (checked on both versions: the copy answers exactly like its source), and an ingest runs as a job
whose progress counts documents, facts and disputes."""
import time
import uuid

import pytest
from starlette.testclient import TestClient

import api.accounts as acc
import api.app as api_app
import api.jobs as jobs
import api.workspaces as ws
from brain.db import Graph
from brain.tools import Ctx, run_tool

from .test_actions import world  # noqa: F401
from .test_workspaces import DOC, _user, accounts_on  # noqa: F401


def test_copy_from_a_template_answers_like_the_template(world):  # noqa: F811
    src = world["g"]
    name = f"ws_copy_{uuid.uuid4().hex[:6]}"
    try:
        ws.copy_into(src, name)
        dst = Graph(name=name, port=src.port)
        own = lambda g: [f["subject_id"] for it in run_tool(Ctx(g), "get_owner", {"entity_id": "system:ledger"})["items"]  # noqa: E731
                         for f in it["facts"] if f["predicate"] == "OWNS"]
        assert own(dst) == own(src) == ["team:payments"]
        assert dst.ro("CALL db.constraints() YIELD status RETURN count(status) AS n")[0]["n"] == \
            src.ro("CALL db.constraints() YIELD status RETURN count(status) AS n")[0]["n"]
    finally:
        Graph(name=name, port=src.port).delete()


def _wait(c, job_id, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = c.get(f"/workspace/jobs/{job_id}").json()
        if j["state"] in ("done", "failed"):
            return j
        time.sleep(0.1)
    raise AssertionError("job didn't finish")


def test_an_upload_runs_as_a_job_with_progress(accounts_on):  # noqa: F811
    a, _ = _user(accounts_on, "a@example.com")
    r = a.post("/workspace/ingest", params={"filename": "billing.md"}, content=DOC)
    assert r.status_code == 200, r.text
    j = _wait(a, r.json()["job_id"])
    assert j["state"] == "done" and j["docs"] == j["total"] == 1 and "facts" in j and "disputes" in j
    assert not a.get("/workspace").json()["empty"]


def test_load_the_demo_company_into_a_workspace(accounts_on, monkeypatch, world):  # noqa: F811
    if world["g"].port != Graph(name="probe").port:
        pytest.skip("GRAPH.COPY stays on one server; the copy itself is checked on both versions above")
    monkeypatch.setattr(api_app, "demo_template", lambda: world["g"])
    a, name = _user(accounts_on, "a@example.com")
    j = _wait(a, a.post("/workspace/demo").json()["job_id"])
    assert j["state"] == "done", j
    sid = a.post("/sessions", json={}).json()["session_id"]
    ev = a.post(f"/sessions/{sid}/turns/sync", json={"text": "Who owns Ledger?"}).json()["events"]
    assert next(e for e in ev if e["event"] == "answer")["assembled"]["lead"].startswith("Payments owns Ledger")


def test_a_job_of_another_workspace_is_not_visible(accounts_on):  # noqa: F811
    a, _ = _user(accounts_on, "a@example.com")
    b, _ = _user(accounts_on, "b@example.com")
    jid = a.post("/workspace/ingest", params={"filename": "billing.md"}, content=DOC).json()["job_id"]
    assert b.get(f"/workspace/jobs/{jid}").status_code == 404
    _wait(a, jid)
