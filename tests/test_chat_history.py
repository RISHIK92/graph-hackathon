"""Chat history per account (Oct 18): each turn's events and trace are kept on its turn span in the workspace
graph, so a reload, a fresh Agent (an API restart or deploy) and the account's next session all see the same
thread, and emptying the workspace clears it."""
import json

from starlette.testclient import TestClient

import api.app as api_app
from api.agent import CHAT_MAX, Agent

from .test_actions import world  # noqa: F401
from .test_workspaces import _user, accounts_on  # noqa: F401


def run(agent, s, text, **kw):
    return list(agent.turn(s, text, **kw))


def answer_of(events):
    return next(e for e in events if e["event"] == "answer")


def test_a_fresh_agent_reads_the_thread_and_trace_from_the_graph(world):
    g, clock = world["g"], world["clock"]
    a = Agent(g, clock)
    s = a.create_session("acct_a", "person:eve")
    ev = run(a, s, "Who owns Ledger?")
    tid = answer_of(ev)["turn_id"]
    clock.tick()
    run(a, s, "Infra owns Ledger now")

    b = Agent(g, clock)   # an API restart: nothing in memory
    assert b.account_session("acct_a") == s.id and b.account_session("acct_b") is None
    turns = b.chat(s.id)
    assert [t["text"] for t in turns] == ["Who owns Ledger?", "Infra owns Ledger now"]
    first = turns[0]
    assert first["turn_id"] == tid and first["actor"] == "person:eve" and first["as_of"] is None
    assert answer_of(first["events"])["assembled"] == json.loads(json.dumps(answer_of(ev)["assembled"], default=str))
    assert any(e["event"] in ("action", "refusal") for e in turns[1]["events"])
    trace = b.stored_trace(s.id, tid)
    assert trace["verification"] == json.loads(json.dumps(a.turn_log[tid]["verification"], default=str))
    assert trace["packs"] and trace["tool_calls"]
    assert b.stored_trace(s.id, "turn_unknown") is None


def test_a_large_turn_drops_its_debug_parts_first(world, monkeypatch):
    g, clock = world["g"], world["clock"]
    monkeypatch.setattr("api.agent.CHAT_MAX", 2_000)
    a = Agent(g, clock)
    s = a.create_session("acct_a", "person:eve")
    run(a, s, "Who owns Ledger?")
    t = Agent(g, clock).chat(s.id)[0]
    assert t["events"] == [] and "queries" not in (t.get("trace") or {})
    assert CHAT_MAX == 200_000


def test_an_anonymous_session_keeps_no_history(world):
    g, clock = world["g"], world["clock"]
    a = Agent(g, clock)
    s = a.create_session("anonymous", "person:eve", anonymous=True)
    run(a, s, "Who owns Ledger?")
    assert a.account_session("anonymous") is None


def _ask(c, text):
    sid = c.post("/sessions", json={}).json()["session_id"]
    ev = c.post(f"/sessions/{sid}/turns/sync", json={"text": text}).json()["events"]
    return sid, answer_of(ev)["turn_id"]


def test_the_account_resumes_its_chat_after_a_reload_and_a_restart(accounts_on, monkeypatch):
    a, name = _user(accounts_on, "a@example.com")
    sid, tid = _ask(a, "Who owns Billing?")
    assert a.post("/sessions", json={}).json()["session_id"] == sid   # a reload resumes the same session
    chat = a.get("/chat").json()
    assert chat["session_id"] == sid and [t["text"] for t in chat["turns"]] == ["Who owns Billing?"]
    assert any(e["event"] == "answer" for e in chat["turns"][0]["events"])

    import api.workspaces as ws
    ws._OPEN.pop(name, None)   # a restart: a fresh Agent with an empty turn_log
    assert a.get("/chat").json()["turns"][0]["turn_id"] == tid
    assert a.get(f"/turns/{tid}/trace").json()["turn_id"] == tid


def test_two_accounts_never_see_each_others_chat(accounts_on):
    a, _ = _user(accounts_on, "a@example.com")
    b, _ = _user(accounts_on, "b@example.com")
    _, tid = _ask(a, "Who owns Billing?")
    assert b.get("/chat").json() == {"session_id": None, "turns": []}
    assert b.get(f"/turns/{tid}/trace").status_code == 404


def test_emptying_the_workspace_clears_the_chat(accounts_on):
    a, _ = _user(accounts_on, "a@example.com")
    sid, _ = _ask(a, "Who owns Billing?")
    assert a.post("/workspace/reset").status_code == 200
    assert a.get("/chat").json() == {"session_id": None, "turns": []}
    assert a.post("/sessions", json={}).json()["session_id"] != sid


def test_accounts_off_has_no_chat():
    assert TestClient(api_app.app).get("/chat").status_code == 404   # sessions stay one per page load
