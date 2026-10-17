"""Item 24 step 4: connectors over recorded payloads (no network). Each yields items with permalinks, and
ingesting them into an empty graph gives entities, facts (CODEOWNERS ownership, ticket assignee and state,
Linear team membership) and spans whose Source keeps the link back to where it was written."""
import json
from pathlib import Path

import httpx
import pytest

from api.agent import Agent
from brain.tools import Ctx, run_tool
from ingest.pipeline import Ingestor
from ingest.sources import CONNECTORS, fetch_docs

FIX = Path(__file__).parent / "fixtures" / "sources"
CFG = {"slack": {"token": "xoxb-test", "channels": ["payments"]}, "linear": {"token": "lin_test"},
       "github": {"token": "ghp_test", "repo": "acme/ledger-service"},
       "jira": {"site": "https://acme.atlassian.net", "email": "a@acme.test", "token": "jira_test", "jql": "project = ING"}}


def _http(kind: str, seen: list) -> httpx.Client:
    data = json.loads((FIX / f"{kind}.json").read_text())

    def handle(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        path = req.url.path
        if kind == "slack":
            return httpx.Response(200, json=data[path.rsplit("/", 1)[1]])
        if kind == "linear":
            return httpx.Response(200, json=data)
        if kind == "jira":
            return httpx.Response(200, json=data)
        key = path.split("/repos/acme/ledger-service/", 1)[1]
        return httpx.Response(200, json=data[key]) if key in data else httpx.Response(404, json={})
    return httpx.Client(transport=httpx.MockTransport(handle))


@pytest.mark.parametrize("kind", list(CONNECTORS))
def test_every_connector_yields_items_with_links(kind):
    seen: list = []
    items = list(CONNECTORS[kind].fetch(_http(kind, seen), CFG[kind]))
    assert items and all(it.url.startswith("https://") for it in items if it.kind != "roster"), items
    assert all(it.system == kind and it.ts > 0 for it in items)
    assert seen and all(CFG[kind]["token"] not in str(r.url) for r in seen)   # tokens only in headers


def _ingest(g, kind):
    docs = fetch_docs(kind, CFG[kind], _http(kind, []))
    Ingestor(g).ingest_docs(docs)
    return docs


def test_github_codeowners_becomes_ownership_and_issues_become_tickets(g):
    _ingest(g, "github")
    pack = run_tool(Ctx(g), "get_owner", {"entity_id": "system:ledger-service"})
    owners = {f["subject_id"] for it in pack["items"] for f in it["facts"] if f["predicate"] == "OWNS"}
    assert "team:payments" in owners
    t = g.ro("MATCH (:Ticket {id:'ticket:ledger-service-12'})-[:ASSIGNED_TO]->(p) RETURN p.id AS p")
    assert t == [{"p": "person:maya"}]
    src = g.ro("MATCH (s:Source {doc_key:'ticket:github:ledger-service#12'}) RETURN s.uri AS u")
    assert src and src[0]["u"] == "https://github.com/acme/ledger-service/issues/12"


def test_linear_issues_and_team_membership(g):
    _ingest(g, "linear")
    assert g.ro("MATCH (:Person {id:'person:maya-chen'})-[:MEMBER_OF]->(t:Team) RETURN t.id AS t") == [{"t": "team:payments"}]
    assert g.ro("MATCH (:Ticket {id:'ticket:pay-7'})-[:ABOUT]->(x) RETURN x.id AS x") == [{"x": "project:core-banking"}]
    assert g.ro("MATCH (s:Source {doc_key:'ticket:linear:PAY-7'}) RETURN s.uri AS u")[0]["u"].startswith("https://linear.app/")


def test_jira_issue_with_component_and_comment(g):
    _ingest(g, "jira")
    assert g.ro("MATCH (:Ticket {id:'ticket:ing-3'})-[:ABOUT]->(x) RETURN x.id AS x") == [{"x": "system:settlement"}]
    assert g.ro("MATCH (:Ticket {id:'ticket:ing-3'})-[:ASSIGNED_TO]->(p) RETURN p.id AS p") == [{"p": "person:omar-haddad"}]
    texts = [r["t"] for r in g.ro("MATCH (s:Span) RETURN s.text AS t")]
    assert any("earlier cut-off" in t for t in texts)


def test_slack_messages_and_threads_with_permalinks(g):
    _ingest(g, "slack")
    rows = g.ro("MATCH (s:Source {kind:'chat'}) RETURN s.uri AS u ORDER BY u")
    assert [r["u"] for r in rows] == ["https://acme.slack.com/archives/payments/p1767225600000100",
                                      "https://acme.slack.com/archives/payments/p1767225660000200"]
    assert g.ro("MATCH (:Span)-[:AUTHORED_BY]->(p:Person {id:'person:omar-haddad'}) RETURN count(*) AS n")[0]["n"] >= 1


def test_an_ingested_workspace_answers_from_its_own_sources(g):
    _ingest(g, "github")
    agent = Agent(g)
    s = agent.create_session("judge", "person:maya")
    ev = list(agent.turn(s, "Who owns Ledger Service?"))
    ans = next(e for e in ev if e["event"] == "answer")
    assert ans["assembled"]["lead"].startswith("Payments owns ledger-service"), ans["assembled"]
