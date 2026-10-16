"""Item 20 step 0: the live checker and escalation. The checker can only make an answer more cautious: a
failed check gets one escalation redraft within 5 s and a re-check; if that fails or times out, the graph's
verified draft is returned; with no checker model, the drafted answer stands and the trace says "skipped".
Every trace lists the models used and the check results. Fake providers only."""
import httpx
import pytest

from api import agent as agent_mod
from api.agent import Agent, deterministic_draft

from .test_actions import world  # noqa: F401
from .test_agent import answer_of, run


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(agent_mod.providers, "llm_available", lambda: True)
    monkeypatch.setattr(agent_mod.providers, "complete", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("off")))
    drafts = []

    def llm(self, text, plan, packs, errors=None, timeout=None, role="drafter"):
        drafts.append((role, timeout))
        base = deterministic_draft(plan, packs, text)
        claims = [dict(c, text=c.get("text", "") + (" (escalated)" if role == "escalation" else "")) for c in base["claims"]]
        if role == "drafter":
            return {"claims": claims, "explanation": "drafted", "model": "deepseek/deepseek-v4.1-flash"}
        return {"claims": claims, "explanation": "escalated", "model": "anthropic/claude-haiku-5.5"}
    monkeypatch.setattr(Agent, "_llm_draft", llm)

    def install(verdicts):
        """verdicts: one per checker call, a probability that the claim is supported, or an exception."""
        seen = []

        def decide(role, state, questions, timeout=None):
            assert role == "checker" and set(questions) == {"supported", "answerable", "injection"}
            v = verdicts[min(len(seen), len(verdicts) - 1)]
            seen.append(state)
            if isinstance(v, Exception):
                raise v
            return {"model": "typesafe/jev-1.14", "cost": 0.00002,
                    "answers": {"supported": {"probability": v}, "answerable": {"probability": v},
                                "injection": {"probability": 0.01}}}
        monkeypatch.setattr(agent_mod.providers, "decide", decide)
        return seen, drafts
    return install


def _turn(world, q="Who owns Ledger?"):
    agent = Agent(world["g"], world["clock"])
    s = agent.create_session("judge", "person:eve")
    ans = answer_of(run(agent, s, q))
    return ans, agent.turn_log[ans["turn_id"]]


def test_a_passing_check_keeps_the_drafted_answer(world, live):
    seen, drafts = live([0.95])
    ans, trace = _turn(world)
    assert trace["check"]["result"] == "pass" and trace["check"]["model"] == "typesafe/jev-1.14"
    assert len(seen) == 1 and "Payments owns Ledger" in seen[0] and len(seen[0].encode()) < 32_000
    assert ans["assembled"]["explanation"] == "drafted"
    roles = {m["role"]: m["model"] for m in trace["models"]}
    assert roles["drafter"] == "deepseek/deepseek-v4.1-flash" and roles["checker"] == "typesafe/jev-1.14"


def test_a_failed_check_escalates_once_and_a_passing_recheck_keeps_it(world, live):
    seen, drafts = live([0.1, 0.9])
    ans, trace = _turn(world)
    assert drafts == [("drafter", agent_mod.DRAFT_TIMEOUT_S), ("escalation", agent_mod.ESCALATION_TIMEOUT_S)] and agent_mod.ESCALATION_TIMEOUT_S <= 5
    assert trace["check"]["result"] == "pass after escalation" and len(seen) == 2
    assert ans["assembled"]["explanation"] == "escalated"
    assert any(m["role"] == "escalation" for m in trace["models"])


def test_a_failed_recheck_returns_the_verified_draft(world, live):
    live([0.1, 0.2])
    ans, trace = _turn(world)
    assert trace["check"]["result"] == "failed twice; returned the graph's verified draft"
    assert not ans["abstained"] and ans["assembled"]["explanation"] == ""
    assert trace["verification"]["draft"] == "deterministic"


def test_an_escalation_timeout_returns_the_verified_draft(world, live, monkeypatch):
    live([0.1])

    def slow(self, text, plan, packs, errors=None, timeout=None, role="drafter"):
        if role == "escalation":
            raise httpx.ReadTimeout("slow")
        return {"claims": deterministic_draft(plan, packs, text)["claims"], "explanation": "drafted"}
    monkeypatch.setattr(Agent, "_llm_draft", slow)
    ans, trace = _turn(world)
    assert trace["check"]["result"] == "escalation timed out; returned the graph's verified draft"
    assert not ans["abstained"] and trace["verification"]["draft"] == "deterministic"


def test_no_checker_model_keeps_the_answer_and_says_skipped(world, live):
    live([agent_mod.providers.LLMUnavailable("checker: both down")])
    ans, trace = _turn(world)
    assert trace["check"]["result"] == "skipped" and "both down" in trace["check"]["reason"]
    assert ans["assembled"]["explanation"] == "drafted" and not ans["abstained"]


def test_offline_answers_record_the_check_as_skipped(world):
    ans, trace = _turn(world)
    assert trace["check"] == {"result": "skipped", "reason": "offline"} and trace["models"] == []


def test_planner_and_drafter_calls_are_bounded(world, monkeypatch):
    """A/B finding (item 20): an unbounded drafter call with retries took up to 94 s. Interactive model calls
    get one bounded attempt per model, then the graph's draft."""
    seen = []

    def complete(messages, schema=None, role=None, timeout=None, **kw):
        seen.append((role, timeout))
        raise httpx.ReadTimeout("slow")
    monkeypatch.setattr(agent_mod.providers, "llm_available", lambda: True)
    monkeypatch.setattr(agent_mod.providers, "complete", complete)
    monkeypatch.setattr(agent_mod.providers, "decide", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("off")))
    ans, trace = _turn(world)
    Agent(world["g"], world["clock"]).plan("Is Ledger fine?", None)   # the rules can't place it: the LLM plans
    assert ("planner", agent_mod.PLAN_TIMEOUT_S) in seen and ("drafter", agent_mod.DRAFT_TIMEOUT_S) in seen, seen
    assert agent_mod.PLAN_TIMEOUT_S <= 6 and agent_mod.DRAFT_TIMEOUT_S <= 10
    assert not ans["abstained"] and trace["verification"]["draft"] == "deterministic"


def test_an_invented_or_missing_citation_returns_the_verified_draft(world, live, monkeypatch):
    """Gate C10: if the drafter drops or invents a citation, the whole answer is the graph's verified draft."""
    live([0.95])

    def llm(self, text, plan, packs, errors=None, timeout=None, role="drafter"):
        base = deterministic_draft(plan, packs, text)["claims"]
        bad = dict(base[0], claim_id="x1", span_ids=["sp_made_up"], text="Infra owns Ledger")
        return {"claims": base + [bad], "explanation": "drafted", "model": "deepseek/deepseek-v4.1-flash"}
    monkeypatch.setattr(Agent, "_llm_draft", llm)
    ans, trace = _turn(world)
    assert trace["draft_error"] == "citation" and trace["verification"]["draft"] == "deterministic"
    assert ans["assembled"]["explanation"] == "" and not ans["abstained"]


def test_the_llm_planner_is_skipped_when_the_rules_are_sure(world, monkeypatch):
    """Gate C12: the LLM's intent is only used when the rules say fact/other, so a confident rule plan with no
    date in the question skips the planner call."""
    seen = []

    def complete(messages, schema=None, role=None, timeout=None, **kw):
        seen.append(role)
        return {"json": {"intent": "ownership", "wants_action": "none", "as_of": ""}, "model": "m"}
    monkeypatch.setattr(agent_mod.providers, "llm_available", lambda: True)
    monkeypatch.setattr(agent_mod.providers, "complete", complete)
    agent = Agent(world["g"], world["clock"])
    s = agent.create_session("judge", "person:eve")
    assert agent.plan("Who owns Ledger?", s)["intent"] == "ownership" and "planner" not in seen
    agent.plan("Who owned Ledger in March 2026?", s)
    agent.plan("Is Ledger fine?", s)
    assert seen.count("planner") == 2
    assert agent_mod.CHECK_TIMEOUT_S <= 2
