"""Item 20 step 0: the eval judges. The decision judge scores the fixed history rubric and agreement with a
reference answer; a low-confidence verdict goes to the second (chat) judge, which decides it, and a 20%
sample goes to both for an agreement rate. Judge ids are written with the results. Fake providers only."""
import pytest

from brain import providers
from evals import answer as ev

Q = {"id": "c8-001", "category": 8, "question": "Who owns Ledger?", "as_of": 0, "belief_at": None,
     "reference_answer": "Recorded: Payments owns Ledger; disputed by a source saying Infra owns Ledger.", "_seed": 1}
ANS = {"abstained": False, "assembled": {"lead": "Recorded: Payments owns Ledger (catalogue); disputed by a chat message "
                                                 "saying “Infra owns Ledger”.", "lines": [], "explanation": ""}}


@pytest.fixture
def judges(monkeypatch):
    monkeypatch.setattr(providers, "llm_available", lambda: True)
    calls = {"decide": [], "complete": []}

    def install(p_rubric, verdict2=1, sampled=False):
        monkeypatch.setattr(ev, "_sampled", lambda q: sampled)

        def decide(role, state, questions, timeout=None):
            calls["decide"].append((role, state))
            assert role == "judge" and set(questions) == {"rubric", "reference"}
            return {"model": "microsoft/microsoft-decision-1", "cost": 0.0001,
                    "answers": {"rubric": {"probability": p_rubric}, "reference": {"score": 0.9}}}

        def complete(messages, schema=None, role=None, **kw):
            calls["complete"].append(role)
            return {"json": {"verdict": verdict2, "reason": "ok"}, "model": "z-ai/glm-5.2"}
        monkeypatch.setattr(providers, "decide", decide)
        monkeypatch.setattr(providers, "complete", complete)
        return calls
    return install


def test_a_confident_judge_decides_alone(judges):
    calls = judges(0.92)
    j = ev.judge_history(Q, ANS)
    assert j["score"] == 1.0 and j["judge"] == "microsoft/microsoft-decision-1" and j["reference_match"] == 0.9
    assert "REFERENCE: Recorded: Payments owns Ledger" in calls["decide"][0][1]
    assert not calls["complete"] and j["judge2"] is None


def test_low_confidence_goes_to_the_second_judge_which_decides(judges):
    calls = judges(0.55, verdict2=0)
    j = ev.judge_history(Q, ANS)
    assert calls["complete"] == ["judge2"] and j["low_confidence"] and j["score"] == 0.0 and j["judge2"] == "z-ai/glm-5.2"


def test_the_sample_is_judged_twice_for_agreement(judges):
    judges(0.95, verdict2=0, sampled=True)
    j = ev.judge_history(Q, ANS)
    assert j["score"] == 1.0 and j["judge2_score"] == 0.0 and j["sampled"]
    rows = [{"history_judge": 1.0, "judge1_score": 1.0, "judge2_score": 0.0},
            {"history_judge": 1.0, "judge1_score": 1.0, "judge2_score": 1.0}, {"history_judge": 0.0}]
    assert ev.judge_agreement(rows) == (0.5, 2)


def test_unjudged_categories_and_offline_runs_skip_the_judge(monkeypatch):
    monkeypatch.setattr(providers, "llm_available", lambda: False)
    assert ev.judge_history(Q, ANS) is None
    assert ev.judge_history({**Q, "category": 3}, ANS) is None


def test_the_sample_is_a_fixed_fifth(monkeypatch):
    ids = [f"c7-{i:03d}" for i in range(500)]
    share = sum(ev._sampled({"id": i, "_seed": 1}) for i in ids) / len(ids)
    assert 0.15 <= share <= 0.25 and ev._sampled({"id": "c7-001", "_seed": 1}) == ev._sampled({"id": "c7-001", "_seed": 1})


def test_cost_per_answer_excludes_the_judges(monkeypatch):
    monkeypatch.setattr(providers, "COSTS", {("planner", "a"): 0.002, ("drafter", "b"): 0.004, ("checker", "c"): 0.001,
                                             ("judge", "d"): 0.5, ("judge2", "e"): 0.5})
    assert ev.cost_per_answer(10) == pytest.approx(0.0007)


def test_stratified_subset_covers_every_category_evenly():
    """The 30-question model A/B (item 20 step 1): 10 per seed, categories taken round robin."""
    qs = [{"id": f"c{c}-{i:03d}", "category": c} for c in (1, 2, 3, 5, 7, 8, 9, 10) for i in range(5)]
    sub = ev.stratified(qs, 10)
    assert len(sub) == 10 and len({q["category"] for q in sub}) == 8
    assert ev.stratified(qs, 10) == sub and ev.stratified(qs, 0) == qs


def test_the_second_judge_grades_phrasing_and_reads_the_reference_as_context(judges):
    """Item 20 review: the second judge saw the REFERENCE under a phrasing-only rubric and failed answers for
    leaving out reference facts; completeness is the decision judge's separate reference score."""
    seen = []

    def complete(messages, schema=None, role=None, **kw):
        seen.append(messages[0]["content"])
        return {"json": {"verdict": 1, "reason": "ok"}, "model": "nvidia/nemotron-3-ultra-550b-a55b"}
    judges(0.5)
    import brain.providers as p
    p.complete = complete
    ev.judge_history(Q, ANS)
    assert ev.JUDGE_RUBRIC.rsplit(" Return JSON", 1)[0] in seen[0]   # the rubric itself is unchanged
    assert "REFERENCE" in seen[0] and "only (a)-(d)" in seen[0]
