"""Item 24 step 1 over HTTP: sign-up, log-in, the demo account, CSRF, rate limits, and the flag."""
import uuid

import pytest
from starlette.testclient import TestClient

import api.accounts as acc
import api.app as api_app
from brain.db import Graph

from .conftest import PORTS
from .test_actions import world  # noqa: F401
from .test_api import api_client  # noqa: F401


@pytest.fixture
def on(monkeypatch):
    name = f"acct_{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("NODUS_ACCOUNTS", "on")
    monkeypatch.setenv("NODUS_ACCOUNTS_GRAPH", name)
    monkeypatch.setenv("NODUS_DEMO_EMAIL", "demo@nodus.test")
    monkeypatch.setenv("NODUS_DEMO_PASSWORD", "demo password 1")
    acc._RATE.clear()
    acc._STORE.clear()
    yield TestClient(api_app.app)
    acc._STORE.clear()
    Graph(name=name, port=PORTS["6.0.1"]).delete()
    Graph(name=name).delete()


def test_routes_are_off_without_the_flag(monkeypatch):
    monkeypatch.delenv("NODUS_ACCOUNTS", raising=False)
    c = TestClient(api_app.app)
    assert c.post("/auth/login", json={"email": "a@b.co", "password": "x" * 8}).status_code == 404
    assert c.get("/auth/me").status_code == 404


def test_signup_login_logout_and_me(on):
    r = on.post("/auth/signup", json={"email": "ana@example.com", "password": "a long password"})
    assert r.status_code == 200 and r.json()["account"]["email"] == "ana@example.com"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    me = on.get("/auth/me").json()
    assert me["account"]["workspace"].startswith("ws_") and me["csrf"]
    assert on.post("/auth/logout").status_code == 403            # cookie writes need the CSRF token
    assert on.post("/auth/logout", headers={"x-csrf-token": me["csrf"]}).status_code == 200
    assert on.get("/auth/me").json() == {"account": None}
    assert on.post("/auth/login", json={"email": "ana@example.com", "password": "wrong!!!!"}).status_code == 401
    assert on.post("/auth/login", json={"email": "ANA@example.com", "password": "a long password"}).status_code == 200


def test_the_demo_button_logs_into_one_shared_account(on):
    a = on.post("/auth/demo").json()["account"]
    b = TestClient(api_app.app).post("/auth/demo").json()["account"]
    assert a["demo"] and a["id"] == b["id"]


def test_login_is_rate_limited_per_ip(on):
    codes = [on.post("/auth/login", json={"email": "x@example.com", "password": "nope nope"}).status_code for _ in range(22)]
    assert codes[-1] == 429 and 401 in codes


def test_the_public_write_token_no_longer_writes_when_accounts_are_on(on, api_client):  # noqa: F811
    r = api_client[0].post("/sessions", json={}, headers={"Authorization": f"Bearer {api_app.settings.public_write_token}"})
    assert r.json()["anonymous"] is True
