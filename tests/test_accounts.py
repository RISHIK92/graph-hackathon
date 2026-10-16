"""Item 24 step 1: accounts, sessions and API keys in their own graph, on both FalkorDB versions."""
import uuid

import pytest

from brain.accounts import AccountError, AccountStore
from brain.db import Graph

from .conftest import PORTS


@pytest.fixture(params=list(PORTS), ids=list(PORTS))
def store(request):
    g = Graph(name=f"acct_{uuid.uuid4().hex[:8]}", port=PORTS[request.param])
    st = AccountStore(g)
    yield st
    g.delete()


def test_signup_login_and_sessions(store):
    a = store.signup("Priya@Example.com ", "correct horse battery")
    assert a["email"] == "priya@example.com" and a["workspace"].startswith("ws_")
    with pytest.raises(AccountError):
        store.signup("priya@example.com", "another password 1")   # one account per email
    with pytest.raises(AccountError):
        store.signup("short@example.com", "short")                 # passwords of 8 or more characters
    with pytest.raises(AccountError):
        store.signup("not-an-email", "long enough pw")
    assert store.login("priya@example.com", "wrong password") is None
    tok, csrf = store.login("PRIYA@example.com", "correct horse battery")
    me = store.session(tok)
    assert me and me["id"] == a["id"] and me["csrf"] == csrf
    store.logout(tok)
    assert store.session(tok) is None


def test_passwords_and_tokens_are_never_stored_in_clear(store):
    store.signup("bob@example.com", "a long password")
    tok, _ = store.login("bob@example.com", "a long password")
    rows = store.g.ro("MATCH (n) RETURN properties(n) AS p")
    text = repr(rows)
    assert "a long password" not in text and tok not in text


def test_an_expired_session_is_refused(store):
    store.signup("eve@example.com", "a long password")
    tok, _ = store.login("eve@example.com", "a long password", ttl_ms=-1)
    assert store.session(tok) is None


def test_api_keys_name_the_workspace(store):
    a = store.signup("jonah@example.com", "a long password")
    key = store.create_key(a["id"])
    assert key.startswith("nodus_") and store.key_account(key)["workspace"] == a["workspace"]
    assert store.key_account("nodus_wrong") is None
    store.revoke_keys(a["id"])
    assert store.key_account(key) is None


def test_ensure_demo_creates_the_shared_account_once(store):
    d1 = store.ensure_demo("demo@nodus.test", "demo password 1")
    d2 = store.ensure_demo("demo@nodus.test", "demo password 1")
    assert d1["id"] == d2["id"] and d1["demo"] is True
    assert store.login("demo@nodus.test", "demo password 1")
