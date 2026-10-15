"""MCP server tests: tool registration (stdio vs HTTP), read tools, write restrictions, and token gating."""
from __future__ import annotations

import dataclasses
import json
from unittest.mock import patch

import pytest

import mcp_server.server as mcp_srv
from brain.actions import Actions, Actor
from brain.config import settings

from .test_actions import _fact, world  # noqa: F401


@pytest.fixture
def mcp_world(world):
    old_g = mcp_srv.G
    old_http = mcp_srv.TRANSPORT["http"]
    mcp_srv.G = world["g"]
    mcp_srv.TRANSPORT["http"] = False
    mcp_srv.HAS_TOKEN.set(False)
    try:
        yield world
    finally:
        mcp_srv.G = old_g
        mcp_srv.TRANSPORT["http"] = old_http
        mcp_srv.HAS_TOKEN.set(False)


# 1. Tool Listing & Registration

def test_mcp_tool_listing_stdio():
    srv = mcp_srv.build(http=False)
    tools = set(srv._tool_manager._tools.keys())

    # All 12 read tools present
    expected_reads = {
        "link_entities", "get_owner", "get_history", "trace_decision",
        "find_experts", "find_paths", "count_related", "rank_by_count", "search_spans", "query_graph",
        "explain_action", "recall_session",
    }
    assert expected_reads.issubset(tools)

    # Standard write tools present
    assert {"route_to_owner", "draft_adr_supersession", "flag_stale_docs", "learn_fact"}.issubset(tools)

    # Risky tools present in stdio mode
    assert "confirm_fact" in tools
    assert "undo_action" in tools
    assert len(tools) == 18


def test_mcp_tool_listing_http_excludes_risky_by_default():
    # In HTTP mode, confirm_fact and undo_action must be absent unless BRAIN_MCP_RISKY_WRITES=on
    srv = mcp_srv.build(http=True)
    tools = set(srv._tool_manager._tools.keys())

    assert "confirm_fact" not in tools
    assert "undo_action" not in tools
    assert "route_to_owner" in tools
    assert "learn_fact" in tools
    assert len(tools) == 16


def test_mcp_tool_listing_http_with_risky_writes_enabled():
    mock_settings = dataclasses.replace(mcp_srv.settings, mcp_risky_writes=True)
    with patch.object(mcp_srv, "settings", mock_settings):
        srv = mcp_srv.build(http=True)
        tools = set(srv._tool_manager._tools.keys())
        assert "confirm_fact" in tools
        assert "undo_action" in tools


def test_mcp_tool_listing_writes_disabled():
    mock_settings = dataclasses.replace(mcp_srv.settings, mcp_writes=False)
    with patch.object(mcp_srv, "settings", mock_settings):
        srv = mcp_srv.build(http=False)
        tools = set(srv._tool_manager._tools.keys())
        # Only read tools registered
        assert len(tools) == 12
        assert "route_to_owner" not in tools
        assert "confirm_fact" not in tools


# 2. Read Tools Execution

def test_mcp_read_tools_untrusted_disclaimer(mcp_world):
    # link_entities
    res_links = json.loads(mcp_srv.link_entities(["Ledger", "Priya"]))
    assert res_links["note"] == mcp_srv.UNTRUSTED
    assert len(res_links["pack"]["items"]) == 2

    # get_owner
    res_owner = json.loads(mcp_srv.get_owner("system:ledger"))
    assert res_owner["note"] == mcp_srv.UNTRUSTED
    assert res_owner["pack"]["tool"] == "get_owner"
    assert res_owner["pack"]["items"][0]["facts"][0]["subject_id"] == "team:payments"

    # get_history
    res_hist = json.loads(mcp_srv.get_history("system:ledger", "OWNS"))
    assert res_hist["note"] == mcp_srv.UNTRUSTED
    assert res_hist["pack"]["tool"] == "get_history"

    # find_paths
    res_paths = json.loads(mcp_srv.find_paths("system:ledger"))
    assert res_paths["note"] == mcp_srv.UNTRUSTED
    assert res_paths["pack"]["tool"] == "find_paths"

    # count_related: Payments owns Ledger in the world fixture
    res_count = json.loads(mcp_srv.count_related("team:payments", "OWNS", "System", direction="out"))
    assert res_count["pack"]["items"][0]["aggregate"]["count"] == 1

    # find_experts
    res_experts = json.loads(mcp_srv.find_experts("system:ledger"))
    assert res_experts["note"] == mcp_srv.UNTRUSTED
    assert res_experts["pack"]["tool"] == "find_experts"


# 3. Write Tools & Restrictions

def test_mcp_write_refused_without_actor(mcp_world):
    # When BRAIN_MCP_ACTOR is empty, write tools are refused
    mock_settings = dataclasses.replace(mcp_srv.settings, mcp_actor="")
    with patch.object(mcp_srv, "settings", mock_settings):
        res = json.loads(mcp_srv.route_to_owner("ticket:rds-42"))
        assert res.get("refused") is True
        assert "no actor configured (BRAIN_MCP_ACTOR)" in res["reason"]


def test_mcp_learn_fact_always_refused(mcp_world):
    mock_settings = dataclasses.replace(mcp_srv.settings, mcp_actor="person:eve")
    with patch.object(mcp_srv, "settings", mock_settings):
        res = json.loads(mcp_srv.learn_fact("Payments owns Ledger"))
        assert res.get("refused") is True
        assert "needs a user-authored turn in a chat session" in res["reason"]


def test_mcp_write_http_requires_bearer_token(mcp_world):
    mock_settings = dataclasses.replace(mcp_srv.settings, mcp_actor="person:eve")
    with patch.object(mcp_srv, "settings", mock_settings):
        mcp_srv.TRANSPORT["http"] = True
        mcp_srv.HAS_TOKEN.set(False)

        # HTTP without token -> refused
        res_no_tok = json.loads(mcp_srv.route_to_owner("ticket:rds-42"))
        assert res_no_tok.get("refused") is True
        assert "write tools need a bearer token over HTTP" in res_no_tok["reason"]

        # HTTP with token -> succeeds
        mcp_srv.HAS_TOKEN.set(True)
        res_with_tok = json.loads(mcp_srv.route_to_owner("ticket:rds-42"))
        assert "action_id" in res_with_tok
        assert res_with_tok["note"] == mcp_srv.UNTRUSTED
        assert res_with_tok["action_id"].startswith("ac_")


def test_mcp_risky_write_confirmation(mcp_world):
    world = mcp_world
    g, clock = world["g"], world["clock"]

    # Eve routes ticket
    acts = Actions(g, clock)
    act_res = acts.route_to_owner(Actor("person:eve"), "ticket:rds-42")
    route_aid = act_res["action_id"]

    # Bob (ineligible) attempts to confirm over MCP -> refused
    mock_bob = dataclasses.replace(mcp_srv.settings, mcp_actor="person:bob")
    with patch.object(mcp_srv, "settings", mock_bob):
        mcp_srv.TRANSPORT["http"] = False
        res_bob = json.loads(mcp_srv.confirm_fact(action_id=route_aid))
        assert res_bob.get("refused") is True

    # Priya (eligible lead) confirms over MCP -> succeeds
    mock_priya = dataclasses.replace(mcp_srv.settings, mcp_actor="person:priya")
    with patch.object(mcp_srv, "settings", mock_priya):
        res_priya = json.loads(mcp_srv.confirm_fact(action_id=route_aid))
        assert "action_id" in res_priya
        conf_aid = res_priya["action_id"]

        # Priya can undo her confirmation over MCP
        res_undo = json.loads(mcp_srv.undo_action(conf_aid))
        assert "action_id" in res_undo


# 4. HTTP ASGI Middleware

@pytest.mark.anyio
async def test_mcp_http_app_token_extraction():
    srv = mcp_srv.build(http=True)
    mcp_srv.http_app(srv)

    # Fake inner ASGI call that inspects HAS_TOKEN
    captured_has_token = []

    async def fake_receive():
        return {"type": "http.request", "body": b""}

    async def fake_send(event):
        pass

    async def test_scope(headers):
        captured_has_token.clear()

        async def inner_check(scope, receive, send):
            captured_has_token.append(mcp_srv.HAS_TOKEN.get())

        with patch.object(srv, "streamable_http_app", return_value=inner_check):
            app = mcp_srv.http_app(srv)
            scope = {
                "type": "http",
                "headers": headers,
            }
            await app(scope, fake_receive, fake_send)

    # 1. No auth header -> HAS_TOKEN is False
    await test_scope([])
    assert captured_has_token == [False]

    # 2. Bad token -> HAS_TOKEN is False
    await test_scope([(b"authorization", b"Bearer bad-token")])
    assert captured_has_token == [False]

    # 3. Public write token -> HAS_TOKEN is True
    await test_scope([(b"authorization", f"Bearer {settings.public_write_token}".encode())])
    assert captured_has_token == [True]

    # 4. Admin token -> HAS_TOKEN is True
    await test_scope([(b"authorization", f"Bearer {settings.admin_token}".encode())])
    assert captured_has_token == [True]


def test_ui_tool_list_matches_the_registered_tools():
    """M16: the UI's "Use from your coding agent" list is the server's own registry, regenerated with
    `python -m mcp_server.server --list-tools > ui/lib/mcp-tools.json`, never a hand-written guess."""
    from pathlib import Path
    shipped = json.loads((Path(__file__).parent.parent / "ui" / "lib" / "mcp-tools.json").read_text())
    assert shipped == mcp_srv.tool_list()
    srv = mcp_srv.build(http=False)
    assert {t["name"] for t in shipped} == set(srv._tool_manager._tools)
