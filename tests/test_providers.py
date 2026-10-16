"""Item 20 step 0: per-role models with fallbacks, the Decisions API client, and cost logging. Fake
transports only; no network."""
import httpx
import pytest

from brain import providers


class Fake:
    """Answers OpenRouter requests per model: a dict, an exception, or an HTTP status."""

    def __init__(self, by_model: dict):
        self.by_model, self.calls = by_model, []

    def __call__(self, url, body, timeout=120, attempts=6):
        self.calls.append((url, body))
        out = self.by_model.get(body["model"], 503)
        if isinstance(out, Exception):
            raise out
        if isinstance(out, int):
            return httpx.Response(out, json={"error": "down"}, request=httpx.Request("POST", url))
        return httpx.Response(200, json=out, request=httpx.Request("POST", url))


def chat(text, cost=0.0001):
    return {"choices": [{"message": {"content": text}}], "usage": {"cost": cost}}


@pytest.fixture
def live(monkeypatch, tmp_path):
    monkeypatch.setattr(providers, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(providers, "llm_available", lambda: True)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    providers.COSTS.clear()

    def install(by_model):
        fake = Fake(by_model)
        monkeypatch.setattr(providers, "_post_retry", fake)
        return fake
    return install


def test_role_uses_its_primary_with_role_settings(live):
    m = providers.role_models("planner")
    fake = live({m[0]: chat('{"intent": "ownership"}')})
    res = providers.complete([{"role": "user", "content": "q"}], schema={"type": "object"}, role="planner")
    assert res["model"] == m[0] and res["json"] == {"intent": "ownership"}
    body = fake.calls[0][1]
    assert body["temperature"] == 0 and body["reasoning"] == {"enabled": False}
    assert body["provider"]["require_parameters"] is True and body["usage"] == {"include": True}
    assert providers.COSTS[("planner", m[0])] == pytest.approx(0.0001)


def test_role_falls_back_when_the_primary_fails(live):
    primary, fallback = providers.role_models("drafter")
    fake = live({primary: 503, fallback: chat("ok")})
    res = providers.complete([{"role": "user", "content": "q"}], role="drafter")
    assert res["model"] == fallback and res["content"] == "ok"
    assert [b["model"] for _, b in fake.calls] == [primary, fallback]
    assert fake.calls[1][1]["reasoning"] == {"effort": "low"}   # Haiku as the fallback runs at low effort
    assert "provider" not in fake.calls[1][1]   # live smoke: Haiku 404s under require_parameters


def test_role_raises_when_every_model_fails(live):
    primary, fallback = providers.role_models("planner")
    live({primary: httpx.ConnectError("x"), fallback: 500})
    with pytest.raises(providers.LLMUnavailable):
        providers.complete([{"role": "user", "content": "q"}], role="planner")


def test_escalation_has_no_fallback():
    assert providers.role_models("escalation") == ["anthropic/claude-haiku-5.5"]


def test_legacy_llm_model_sets_planner_drafter_and_extractor_alone(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "poolside/laguna-xs-2.1")
    for role in ("planner", "drafter", "extractor"):
        assert providers.role_models(role) == ["poolside/laguna-xs-2.1"], role
    assert providers.role_models("checker")[0] == "typesafe/jev-1.14"


def test_role_env_overrides(monkeypatch):
    monkeypatch.setenv("MODEL_CHECKER", "nace-ai/drex-v2.0")
    monkeypatch.setenv("MODEL_CHECKER_FALLBACK", "none")
    assert providers.role_models("checker") == ["nace-ai/drex-v2.0"]


def test_decide_posts_to_the_alpha_endpoint_and_falls_back(live):
    primary, fallback = providers.role_models("checker")
    answer = {"answers": {"supported": {"type": "noul", "noul": 0.93}}, "usage": {"cost": 0.00002}}
    fake = live({primary: 404, fallback: answer})
    qs = {"supported": {"type": "noul", "instructions": "Is the claim supported?", "criteria": {"true": "a", "false": "b"}}}
    res = providers.decide("checker", "x" * 40_000, qs)
    url, body = fake.calls[-1]
    assert url == providers.DECISIONS_URL and body["model"] == fallback and body["questions"] == qs
    assert len(body["state"].encode()) <= providers.DECISION_STATE_MAX   # under 32 KB per request
    assert res["model"] == fallback and providers.decision_p(res, "supported") == pytest.approx(0.93)
    assert providers.COSTS[("checker", fallback)] == pytest.approx(0.00002)
    again = providers.decide("checker", "x" * 40_000, qs)   # cached like complete
    assert again["answers"] == res["answers"]
    assert [b["model"] for _, b in fake.calls].count(fallback) == 1   # the fallback's answer came from cache


def test_decision_p_reads_the_documented_answer_shapes():
    """The alpha API's shapes (checked against its reference, Oct 16): noul is a probability; score is the
    probability-weighted position on the criteria list, normalised to 0..1."""
    assert providers.decision_p({"answers": {"q": {"type": "noul", "noul": 0.96}}}, "q") == pytest.approx(0.96)
    score = {"type": "score", "score": 1.5, "legend": {"0": "a", "1": "b", "2": "c"}}
    assert providers.decision_p({"answers": {"q": score}}, "q") == pytest.approx(0.75)


def test_every_shipped_decision_question_has_the_documented_criteria():
    from api.agent import CHECK_QUESTIONS
    from evals.answer import JUDGE_QUESTIONS
    from ingest.extract import _SCREEN
    for qs in (CHECK_QUESTIONS, JUDGE_QUESTIONS, _SCREEN):
        for name, q in qs.items():
            assert q["instructions"], name
            if q["type"] == "noul":
                assert set(q["criteria"]) == {"true", "false"}, name
            elif q["type"] == "score":
                assert isinstance(q["criteria"], list) and len(q["criteria"]) >= 2, name


def test_decision_p_reads_scores_and_booleans():
    assert providers.decision_p({"answers": {"q": {"score": 0.4}}}, "q") == pytest.approx(0.4)
    assert providers.decision_p({"answers": {"q": {"answer": False}}}, "q") == 0.0
    assert providers.decision_p({"answers": {"q": {"answer": "yes", "probability": 0.8}}}, "q") == pytest.approx(0.8)
    assert providers.decision_p({"answers": {}}, "q") is None


def test_the_cache_folder_can_be_moved_for_a_cold_run(tmp_path):
    import subprocess
    import sys
    out = subprocess.run([sys.executable, "-c", "from brain import providers; print(providers.CACHE_DIR)"],
                         env={**__import__("os").environ, "BRAIN_LLM_CACHE": str(tmp_path)}, capture_output=True, text=True)
    assert out.stdout.strip() == str(tmp_path)


def test_deepseek_only_settings_stay_off_other_models(live, monkeypatch):
    """A/B finding (item 20): legacy LLM_MODEL=laguna got DeepSeek's reasoning-off and require_parameters
    settings, and every laguna call failed, so that arm measured the graph's deterministic draft only."""
    monkeypatch.setenv("LLM_MODEL", "poolside/laguna-xs-2.1")
    fake = live({"poolside/laguna-xs-2.1": chat("ok")})
    providers.complete([{"role": "user", "content": "q"}], role="planner")
    body = fake.calls[0][1]
    assert "reasoning" not in body and "provider" not in body, body


def test_planner_drafter_and_second_judge_have_a_default_pinned_provider(live, monkeypatch):
    """Gate A1: the serving provider is a pinned one. DeepSeek's own endpoint for the planner and drafter,
    DeepInfra (which serves both nemotron and GLM) for the second judge; MODEL_<ROLE>_PROVIDER overrides."""
    deepseek = ["deepinfra/fp8/priority", "deepinfra/fp8", "cloudflare", "coreweave/fp8"]
    for role, pin in (("planner", deepseek), ("drafter", deepseek), ("judge2", ["deepinfra"])):
        body = providers._role_body(role, providers.role_models(role)[0])["provider"]
        assert body["order"] == pin and body["allow_fallbacks"] is False and body["require_parameters"] is True, role
        assert "deepinfra/fp8/flex" in body["ignore"]   # the low-priority queue tier, never
    monkeypatch.setenv("MODEL_PLANNER_PROVIDER", "fireworks,together")
    assert providers._role_body("planner", "deepseek/deepseek-v4.1-flash")["provider"]["order"] == ["fireworks", "together"]


def test_a_bounded_call_has_a_wall_clock_deadline(monkeypatch):
    """A/B finding: OpenRouter keeps a slow request alive with keep-alive bytes, so httpx's per-read timeout
    never fired and a "10 s" drafter call ran 170 s. A bounded call now stops at its deadline."""
    import time as _t

    class Trickle(httpx.SyncByteStream):
        def __iter__(self):
            for _ in range(50):
                _t.sleep(0.05)
                yield b" "
            yield b'{"choices": []}'

    monkeypatch.setattr(providers, "TRANSPORT", httpx.MockTransport(lambda req: httpx.Response(200, stream=Trickle())))
    import dataclasses
    monkeypatch.setattr(providers, "settings", dataclasses.replace(providers.settings, openrouter_key="test"))
    t0 = _t.time()
    with pytest.raises(httpx.TimeoutException):
        providers._post_retry(providers.CHAT_URL, {"model": "m"}, timeout=0.5, attempts=1)
    assert _t.time() - t0 < 1.5
    fast = httpx.MockTransport(lambda req: httpx.Response(200, json={"ok": 1}))
    monkeypatch.setattr(providers, "TRANSPORT", fast)
    assert providers._post_retry(providers.CHAT_URL, {"model": "m"}, timeout=0.5, attempts=1).json() == {"ok": 1}
