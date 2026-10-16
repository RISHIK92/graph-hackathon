"""Item 20 step 7 B: a full live run that can't be wasted. Abort early on fallbacks, role errors, cost or
latency; resume from completed rows with no double spend; model errors are counted per role, never a silent
fallback. Fake providers and rows only."""
import httpx
import pytest

from brain import providers
from evals import answer as ev

from .test_actions import world  # noqa: F401


@pytest.fixture(autouse=True)
def _live(monkeypatch):
    """The guard applies to live runs; tests that need offline set it back."""
    monkeypatch.setattr(providers, "llm_available", lambda: True)


def _row(i, drafted="llm", label="1", latency=900.0):
    return {"seed": 1, "variant": "D", "id": f"c{label}-{i:03d}", "label": label, "abstained": False,
            "drafted": drafted, "latency_ms": latency}


def test_the_guard_waits_for_fifteen_answers():
    rows = [_row(i, drafted="deterministic") for i in range(14)]
    assert ev.Guard().reason(rows, {}, 0.0) is None


def test_the_guard_stops_on_deterministic_fallbacks():
    rows = [_row(i) for i in range(12)] + [_row(12 + i, "deterministic") for i in range(3)]
    assert "fell back" in ev.Guard().reason(rows, {}, 0.0)
    fixed = [_row(i) for i in range(13)] + [_row(13, "deterministic", "4"), _row(14, "deterministic", "10")]
    assert ev.Guard().reason(fixed, {}, 0.0) is None   # decision traces and counts never use the drafter


def test_the_guard_stops_on_role_errors_cost_and_latency():
    rows = [_row(i) for i in range(20)]
    assert "planner" in ev.Guard().reason(rows, {"planner": {"calls": 40, "errors": 3}}, 0.0)
    assert ev.Guard().reason(rows, {"planner": {"calls": 40, "errors": 2}}, 0.0) is None
    assert "cost" in ev.Guard(ab_cost_per_answer=0.001).reason(rows, {}, 0.0031 * 20)   # over 3x the A/B
    slow = rows[:-2] + [_row(98, latency=20_000), _row(99, latency=21_000)]
    assert "p95" in ev.Guard().reason(slow, {}, 0.0)


def test_progress_resumes_completed_rows(tmp_path):
    p = ev.Progress(tmp_path, "D")
    p.add(_row(1))
    p.add(_row(2))
    again = ev.Progress(tmp_path, "D")
    assert again.done({"id": "c1-001", "_seed": 1}) and not again.done({"id": "c1-003", "_seed": 1})
    assert [r["id"] for r in again.rows] == ["c1-001", "c1-002"]


def test_model_errors_are_counted_per_role(monkeypatch, tmp_path):
    monkeypatch.setattr(providers, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(providers, "llm_available", lambda: True)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    providers.STATS.clear()

    def post(url, body, timeout=120, attempts=6):
        if body["model"].startswith("deepseek"):
            return httpx.Response(429, json={"error": "rate"}, request=httpx.Request("POST", url))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}, request=httpx.Request("POST", url))
    monkeypatch.setattr(providers, "_post_retry", post)
    assert providers.complete([{"role": "user", "content": "q"}], role="planner", timeout=6)["content"] == "ok"
    assert providers.STATS["planner"] == {"calls": 2, "errors": 1}


@pytest.mark.parametrize("err", [httpx.ReadTimeout("slow"), RuntimeError("429")])
def test_draft_errors_reach_the_trace(world, monkeypatch, err):
    from api import agent as agent_mod
    from api.agent import Agent
    from .test_agent import answer_of, run

    def draft(self, *a, **k):
        raise err
    monkeypatch.setattr(agent_mod.providers, "llm_available", lambda: True)
    monkeypatch.setattr(agent_mod.providers, "complete", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("off")))
    monkeypatch.setattr(agent_mod.providers, "decide", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("off")))
    monkeypatch.setattr(Agent, "_llm_draft", draft)
    agent = Agent(world["g"], world["clock"])
    s = agent.create_session("judge", "person:eve")
    ans = answer_of(run(agent, s, "Who owns Ledger?"))
    assert agent.turn_log[ans["turn_id"]]["draft_error"] in ("timeout", "failed")


def test_run_resumes_and_aborts(monkeypatch, tmp_path):
    """run() skips rows already in the progress file and stops when the guard trips, writing what it has."""
    import json as _json
    from brain.config import ROOT
    for s in (1,):
        (tmp_path / f"questions-seed{s}.jsonl").write_text(
            "\n".join(_json.dumps({"id": f"c1-{i:03d}", "category": 1, "question": "q", "must_abstain": False,
                                   "anchor": False}) for i in range(30)))
    assert (ROOT / "world" / "seeds" / "1").exists()
    calls = []

    def evaluate(agent, q, as_of, v="D"):
        calls.append(q["id"])
        return {"id": q["id"], "category": 1, "label": "1", "abstained": False, "must_abstain": False,
                "drafted": "deterministic" if len(calls) > 16 else "llm", "latency_ms": 100.0, "draft_citations": 0}
    monkeypatch.setattr(ev, "evaluate", evaluate)
    monkeypatch.setattr(ev, "VARIANT_AGENTS", {"D": lambda g: None})
    monkeypatch.setattr(ev, "_pool_map", lambda fn, xs: [fn(x) for x in xs])
    monkeypatch.setattr(ev, "judge_agreement", lambda rows: (None, 0))
    monkeypatch.setattr(providers, "STATS", {})
    with pytest.raises(ev.EvalAborted, match="fell back"):
        ev.run([1], tmp_path, per_cat=30, variants=["D"])
    first = len(calls)
    assert 17 <= first < 30 and "ABORTED" in (tmp_path / "answer-summary.md").read_text()
    calls.clear()
    with pytest.raises(ev.EvalAborted):   # a resume re-checks the rows it has and stops again, spending nothing
        ev.run([1], tmp_path, per_cat=30, variants=["D"])
    assert calls == [] or len(calls) <= 1
    assert len(_json.loads("[" + ",".join((tmp_path / "answer-D.progress.jsonl").read_text().split("\n")[:-1]) + "]")) >= first


def test_report_has_rates_and_the_models_and_providers_that_served():
    rows = [{**_row(1), "models": [{"role": "planner", "model": "deepseek/x", "provider": "DeepInfra"},
                                   {"role": "drafter", "model": "deepseek/x", "provider": "DeepInfra"},
                                   {"role": "checker", "model": "typesafe/jev-1.14", "provider": "TypeSafe", "result": "fail"},
                                   {"role": "escalation", "model": "anthropic/h", "provider": "Anthropic"}],
             "check": "pass after escalation", "plan_ms": 900, "draft_ms": 2000, "verify_ms": 1500},
            {**_row(2, drafted="deterministic"), "models": [], "check": "pass", "plan_ms": 800, "draft_ms": 10,
             "verify_ms": 300},
            {**_row(3), "models": [], "check": "failed twice; returned the graph's verified draft", "plan_ms": 1, "draft_ms": 1,
             "verify_ms": 1}]
    lines = ev.run_report(rows)
    text = "\n".join(lines)
    assert "deterministic fallback | 1 of 3" in text and "escalation | 1 of 3" in text and "checker blocked | 2 of 3" in text
    assert "planner: deepseek/x via DeepInfra (1)" in text and "checker: typesafe/jev-1.14 via TypeSafe (1)" in text


def test_question_files_are_hashed_into_the_results(tmp_path):
    (tmp_path / "questions-seed1.jsonl").write_text("a")
    ev.write_question_hashes(tmp_path, [1])
    assert (tmp_path / "questions.sha256").read_text().startswith(
        "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb  questions-seed1.jsonl")


def test_checker_blocks_are_not_fallbacks():
    rows = [_row(i) for i in range(12)] + [{**_row(12 + i, "deterministic"), "check": "failed twice; returned the graph's "
                                            "verified draft"} for i in range(3)]
    assert ev.Guard().reason(rows, {}, 0.0) is None
    assert ev.fell_back({**_row(1, "deterministic"), "label": "4-pending"}) is False


def test_the_guard_needs_three_events_before_it_aborts():
    """Re-run finding: on a 29-question arm one fallback (1 of 9) or one drafter error (1 of 14) tripped the
    10% and 5% rules. An abort needs at least 3 fallbacks or 3 errors as well as the rate."""
    rows = [_row(i) for i in range(16)] + [_row(16, "deterministic"), _row(17, "deterministic")]
    assert ev.Guard().reason(rows, {}, 0.0) is None
    assert ev.Guard().reason(rows + [_row(18, "deterministic")], {}, 0.0)
    assert ev.Guard().reason(rows[:16], {"drafter": {"calls": 14, "errors": 2}}, 0.0) is None
    assert ev.Guard().reason(rows[:16], {"drafter": {"calls": 30, "errors": 3}}, 0.0)


def test_offline_runs_are_never_aborted_for_deterministic_drafts(monkeypatch):
    """Found running C8: offline every answer is the graph's draft by design, so the guard applies only live."""
    monkeypatch.setattr(providers, "llm_available", lambda: False)
    rows = [_row(i, "deterministic") for i in range(20)]
    assert ev.Guard().reason(rows, {}, 0.0) is None
