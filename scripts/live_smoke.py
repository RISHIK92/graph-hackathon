"""Item 20 step 0 live smoke check: confirm each role's model id, request shape and the alpha Decisions
endpoint with one tiny call per model (at most 3 calls per role, the user-approved budget). Prints the
model, outcome, latency, usage.cost and the shape of a decision response; never a key or a prompt body.

    .venv/bin/python scripts/live_smoke.py [--roles planner checker ...]
"""
from __future__ import annotations

import argparse
import json
import time

import httpx

from brain import providers
from brain.config import ROLE_MODELS, settings

CHAT_ROLES = ("extractor", "planner", "drafter", "escalation", "judge2")
DECISION_ROLES = ("screen", "checker", "judge")
QUESTION = {"ok": {"type": "noul", "instructions": "Does the text say that Payments owns Ledger?",
                   "criteria": "Yes if it states it."}}


def endpoints(model: str) -> str:
    r = httpx.get(f"https://openrouter.ai/api/v1/models/{model}/endpoints", timeout=20,
                  headers={"Authorization": f"Bearer {settings.openrouter_key}"})
    if r.status_code != 200:
        return f"endpoints HTTP {r.status_code}"
    eps = (r.json().get("data") or {}).get("endpoints") or []
    return f"{len(eps)} endpoint(s): " + ", ".join(sorted({e.get("provider_name", "?") for e in eps}))[:120]


def call(role: str, model: str) -> dict:
    t0 = time.time()
    before = dict(providers.COSTS)
    try:
        if role in DECISION_ROLES:
            body = {"model": model, "state": "Payments owns Ledger.", "questions": QUESTION}
            r = providers._post_retry(providers.DECISIONS_URL, body, timeout=30, attempts=1)
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            providers._log_cost(role, model, data)
            out = {"ok": r.status_code == 200, "http": r.status_code,
                   "shape": json.dumps({k: (sorted(v) if isinstance(v, dict) else type(v).__name__) for k, v in data.items()})[:300],
                   "p_ok": providers.decision_p({"answers": data.get("answers") or data.get("results") or {}}, "ok")}
        else:
            res = providers._complete_one([{"role": "user", "content": "Reply with the JSON {\"ok\": true}."}],
                                          {"type": "object", "properties": {"ok": {"type": "boolean"}}}, None, model,
                                          0.0, 30, role)
            out = {"ok": res.get("json") == {"ok": True}, "reply": (res.get("content") or "")[:60]}
    except Exception as e:  # noqa: BLE001
        out = {"ok": False, "error": str(e)[:200]}
    cost = sum(providers.COSTS.values()) - sum(before.values())
    return {"role": role, "model": model, "ms": round((time.time() - t0) * 1000), "cost": round(cost, 6), **out}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--roles", nargs="+", default=list(ROLE_MODELS))
    a = ap.parse_args()
    if not providers.llm_available():
        raise SystemExit("needs OPENROUTER_API_KEY and BRAIN_LLM on")
    providers.CACHE_DIR = providers.CACHE_DIR.parent / "llm-smoke"   # a smoke call never answers from cache
    for role in a.roles:
        for model in providers.role_models(role)[:3]:
            print(json.dumps({**call(role, model), "endpoints": endpoints(model)}))
    print(json.dumps({"total_cost_usd": round(sum(providers.COSTS.values()), 6)}))


if __name__ == "__main__":
    main()
