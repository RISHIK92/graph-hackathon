"""Optional LLM paraphrase of prose sentences (05 §3.2).

A no-op unless BOTH `OPENROUTER_API_KEY` is set in the environment AND the build was asked
for it (`python -m world.build --paraphrase`). No network is touched otherwise. When active,
each sentence is rewritten once per (seed, text) with a fixed seed, cached in
`world/paraphrase_cache.json`, and must still contain every entity name/alias it was given
(case-sensitive); otherwise it is re-rolled up to 3 times and the template text is kept.
Manifest offsets are computed after paraphrase, so they stay exact either way.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

CACHE_PATH = Path(__file__).resolve().parent / "paraphrase_cache.json"
_cache: dict[str, str] | None = None


def enabled(requested: bool) -> bool:
    return bool(requested and os.environ.get("OPENROUTER_API_KEY"))


def _load() -> dict[str, str]:
    global _cache
    if _cache is None:
        _cache = json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}
    return _cache


def _save() -> None:
    if _cache is not None:
        CACHE_PATH.write_text(json.dumps(_cache, indent=1, sort_keys=True, ensure_ascii=False) + "\n")


def _call(text: str, names: list[str], seed: int) -> str:  # pragma: no cover - network
    import urllib.request

    model = os.environ.get("LLM_MODEL", "openai/gpt-4o-mini")
    prompt = ("Rewrite this workplace sentence in different words, same meaning, one sentence. "
              f"Keep these names exactly as written: {', '.join(names)}. Keep any YYYY-MM-DD date. "
              f"Sentence: {text}")
    body = json.dumps({"model": model, "seed": seed, "temperature": 0.7,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=body, headers={
        "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.loads(r.read())["choices"][0]["message"]["content"].strip()
    return " ".join(out.split())


def paraphrase(text: str, names: list[str], seed: int, requested: bool = False) -> str:
    """Return a paraphrase of `text` that keeps every name in `names`, or `text` itself."""
    if not enabled(requested):
        return text
    cache = _load()
    key = hashlib.sha256(f"{seed}\x1f{text}".encode()).hexdigest()[:24]
    if key in cache:
        return cache[key]
    result = text
    for attempt in range(3):  # pragma: no cover - network
        try:
            cand = _call(text, names, seed * 10 + attempt)
        except Exception:
            break
        if all(n in cand for n in names) and '"' not in cand and "\\" not in cand:
            result = cand
            break
    cache[key] = result
    _save()
    return result
