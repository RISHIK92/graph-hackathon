"""Item 20: the enterprise answer contract, the same shape for every intent. Line 1 answers in one sentence
with its own citations; at most 3 supporting lines, each cited, none repeating another or the lead; a status
line and one next step only when they apply; no internal ids; a length cap. The final claims are exactly
what is shown, so every citation backs a line."""
import re

import pytest

from api.agent import Agent

from .conftest import Clock
from .test_actions import world  # noqa: F401
from .test_agent import _counting_world, answer_of, run
from .test_templates import fx  # noqa: F401

IDS = re.compile(r"\b(?:system|person|team|project|decision|ticket):[a-z0-9-]+|\b(?:as|sp|ac)_[0-9a-f]{6,}|\b1[67]\d{11}\b")

FX_QUESTIONS = ["Who owns Ledger?", "Route RDS-42 to the owner", "What breaks if Ledger goes down, and who do I tell?",
                "Who knows about Ledger?", "Why did ADR-002 replace ADR-001?", "What is the status of ADR-002?",
                "Is there a draft that would supersede ADR-002?", "What does Checkout depend on?",
                "Which project is Ledger part of?", "Tell me about Ledger"]
COUNTING_QUESTIONS = ["How many systems depend directly on Ledger?", "Which systems are most critical?",
                      "How is Bob Okafor connected to Ledger?", "Who are our single points of failure?",
                      "Where are our knowledge gaps?"]


def _check(ans: dict, q: str) -> None:
    a = ans["assembled"]
    assert not ans["abstained"], q
    assert a["lead"], q
    assert len(a["lines"]) <= 3, (q, a["lines"])
    texts = [l["text"] for l in a["lines"]]
    assert len(set(texts)) == len(texts), (q, texts)
    claims = {c["claim_id"]: c for c in ans["claims"]}
    assert a["lead_claims"] and all(claims[c].get("span_ids") or claims[c].get("assertion_ids") for c in a["lead_claims"]), q
    for l in a["lines"]:
        assert l["text"] not in a["lead"], (q, l["text"])
        assert claims[l["claim_id"]].get("span_ids") or claims[l["claim_id"]].get("assertion_ids"), (q, l)
    shown = set(a["lead_claims"]) | {x for l in a["lines"] for x in [l["claim_id"], *l["also"]]}
    extra = [c for c in ans["claims"] if c["claim_id"] not in shown and not (c.get("disputed") or c.get("tense") == "proposed")]
    assert not extra, (q, [c.get("text") for c in extra])
    full = " ".join([a["lead"], *texts, (a.get("status") or {}).get("text", ""), a.get("next") or ""])
    assert len(full) <= 700, (q, len(full))
    assert not IDS.search(full), (q, IDS.search(full).group(0))


@pytest.mark.parametrize("q", FX_QUESTIONS)
def test_contract_on_fixture_questions(fx, q):  # noqa: F811
    agent = Agent(fx.g, Clock(fx.now + 10))
    s = agent.create_session("judge", "person:eve")
    _check(answer_of(run(agent, s, q)), q)


@pytest.mark.parametrize("q", COUNTING_QUESTIONS)
def test_contract_on_counting_and_algorithm_questions(world, q):  # noqa: F811
    _counting_world(world)
    agent = Agent(world["g"], world["clock"])
    s = agent.create_session("judge", "person:eve")
    _check(answer_of(run(agent, s, q)), q)


def test_disputed_answer_has_a_status_and_one_next_step(fx):  # noqa: F811
    agent = Agent(fx.g, Clock(fx.now + 10))
    s = agent.create_session("judge", "person:eve")
    ans = answer_of(run(agent, s, "Who owns Ledger?"))
    a = ans["assembled"]
    _check(ans, "dispute")
    assert a["lead"].startswith("Recorded: Payments owns Ledger"), a["lead"]
    assert a.get("status") is None   # the dispute lead already says it and who can settle it
    assert a["next"] == "Ask Priya Raman to confirm.", a.get("next")


def test_past_belief_answer_says_when(fx):  # noqa: F811
    agent = Agent(fx.g, Clock(fx.now + 10))
    s = agent.create_session("judge", "person:eve")
    ans = answer_of(run(agent, s, "Who owned Ledger?", as_of=3))
    _check(ans, "as of")
    assert ans["assembled"]["lead"].startswith("Platform owned Ledger on "), ans["assembled"]["lead"]


def test_the_stored_agent_turn_keeps_the_lead(fx):  # noqa: F811
    """Conversation recall reads the agent's stored turn; the answer's first line is in it."""
    agent = Agent(fx.g, Clock(fx.now + 10))
    s = agent.create_session("judge", "person:eve")
    lead = answer_of(run(agent, s, "What is the status of ADR-002?"))["assembled"]["lead"]
    rows = fx.g.ro("MATCH (:Source {id:$s})-[:HAS_SPAN]->(sp:Span {author_role:'agent'}) RETURN sp.text AS t",
                   {"s": s.id}, template="test")
    assert rows and rows[0]["t"].startswith(lead), (lead, rows)
