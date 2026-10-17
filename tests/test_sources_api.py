"""Item 24 step 4 over HTTP: the sources list says what each connector needs, a connection is stored for the
workspace, and a sync runs as a job that ingests into that workspace only (recorded payloads, no network)."""
import time

import pytest

import api.app as api_app

from .test_sources import CFG, _http
from .test_workspaces import _user, accounts_on  # noqa: F401


@pytest.fixture
def keyed(accounts_on, monkeypatch):  # noqa: F811
    monkeypatch.setenv("NODUS_SECRET_KEY", "a test secret key")
    for k in ("SLACK_CLIENT_ID", "SLACK_CLIENT_SECRET", "SLACK_REDIRECT_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(api_app, "_source_http", lambda kind: _http(kind, []))
    return accounts_on


def test_the_sources_list_says_what_each_one_needs(keyed):
    a, _ = _user(keyed, "a@example.com")
    rows = {r["kind"]: r for r in a.get("/workspace/sources").json()}
    assert set(rows) >= {"slack", "linear", "github", "jira", "docs"}
    assert rows["slack"]["missing"] == ["SLACK_CLIENT_ID", "SLACK_CLIENT_SECRET", "SLACK_REDIRECT_URL"]
    assert not rows["github"]["missing"] and not rows["github"]["connected"]
    assert a.get("/auth/slack/start", follow_redirects=False).status_code == 503


def test_connect_and_sync_github_into_the_workspace(keyed):
    a, _ = _user(keyed, "a@example.com")
    b, _ = _user(keyed, "b@example.com")
    assert a.post("/workspace/sources/github", json={"config": {"repo": "acme/ledger-service"}}).status_code == 400
    assert a.post("/workspace/sources/github", json={"config": CFG["github"]}).status_code == 200
    assert {r["kind"]: r for r in a.get("/workspace/sources").json()}["github"]["connected"]
    jid = a.post("/workspace/sources/github/sync").json()["job_id"]
    for _ in range(200):
        j = a.get(f"/workspace/jobs/{jid}").json()
        if j["state"] != "running":
            break
        time.sleep(0.05)
    assert j["state"] == "done" and j["docs"] >= 3, j
    assert not a.get("/workspace").json()["empty"] and b.get("/workspace").json()["empty"]
    assert b.post("/workspace/sources/github/sync").status_code == 400   # b connected nothing
    assert a.delete("/workspace/sources/github").status_code == 200
