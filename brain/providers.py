"""Provider interface for the LLM and embeddings (07 §1, A27).

`complete(messages, schema=None, tools=None)` and `embed(texts)`. With `OPENROUTER_API_KEY` set,
OpenRouter is used; otherwise deterministic local stand-ins run so the whole system works offline:
a hashed bag-of-features embedding and no LLM (callers fall back to rule-based paths).
All responses are cached by (prompt hash, model), so eval reruns are free (06 §7).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx

from .config import ROOT, settings

CACHE_DIR = ROOT / ".cache" / "llm"
_NO_SCHEMA: set[str] = set()


def _with_schema_prompt(messages: list[dict], schema: dict) -> list[dict]:
    note = ("\n\nReply with ONLY a JSON object (no prose, no code fences) matching this JSON schema:\n"
            + json.dumps(schema))
    msgs = [dict(m) for m in messages]
    if msgs and msgs[0]["role"] == "system":
        msgs[0]["content"] += note
    else:
        msgs.insert(0, {"role": "system", "content": note.strip()})
    return msgs
_TOKEN = re.compile(r"[a-z0-9]+")


class LLMUnavailable(Exception):
    pass


def llm_available() -> bool:
    """Completions are on when a key is set and BRAIN_LLM isn't "off". Embeddings are independent
    (see `embed`), so a retrieval run can use the graph's real embeddings with the LLM switched off."""
    return bool(settings.openrouter_key) and os.environ.get("BRAIN_LLM", "on") != "off"


def embed_available() -> bool:
    return bool(settings.openrouter_key) and settings.embed_provider != "local"


def _cache_path(kind: str, key: str) -> Path:
    return CACHE_DIR / kind / key[:2] / f"{key}.json"


CACHE_STATS = {"hits": 0, "misses": 0}


def _cached(kind: str, payload: Any, fn):
    key = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    path = _cache_path(kind, key)
    if path.exists():
        CACHE_STATS["hits"] += 1
        try:
            return json.loads(path.read_text())
        except Exception:
            CACHE_STATS["hits"] -= 1
    CACHE_STATS["misses"] += 1
    out = fn()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(out))
    tmp.replace(path)
    return out


def _post_retry(url: str, body: dict) -> httpx.Response:
    """POST with backoff on 429 / 5xx and on transient transport errors (SSL EOF, resets, timeouts),
    which otherwise abort an hour-long ingestion."""
    last: Exception | None = None
    for attempt in range(6):
        try:
            r = httpx.post(url, json=body, timeout=120, headers={"Authorization": f"Bearer {settings.openrouter_key}"})
        except (httpx.TransportError, httpx.RemoteProtocolError) as e:
            last = e
            time.sleep(min(30, 2 ** attempt))
            continue
        if r.status_code not in (429, 500, 502, 503, 524):
            return r
        time.sleep(min(30, 2 ** attempt))
    if last:
        raise last
    return r


def complete(messages: list[dict], schema: dict | None = None, tools: list[dict] | None = None,
             model: str | None = None, temperature: float = 0.0) -> dict:
    """Returns {"content": str, "tool_calls": [...], "json": parsed-or-None}."""
    model = model or settings.llm_model
    payload = {"model": model, "messages": messages, "schema": schema, "tools": tools, "t": temperature}

    def call() -> dict:
        if not llm_available():
            raise LLMUnavailable("OPENROUTER_API_KEY not set")
        def post(msgs: list[dict], use_schema: bool) -> httpx.Response:
            body: dict[str, Any] = {"model": model, "messages": msgs, "temperature": temperature}
            if schema and use_schema:
                body["response_format"] = {"type": "json_schema",
                                           "json_schema": {"name": "out", "strict": False, "schema": schema}}
            if tools:
                body["tools"] = tools
            return _post_retry("https://openrouter.ai/api/v1/chat/completions", body)

        if schema and model in _NO_SCHEMA:
            r = post(_with_schema_prompt(messages, schema), use_schema=False)
        else:
            r = post(messages, use_schema=bool(schema))
            if schema and r.status_code == 400:
                # The model rejects response_format (common on free-tier models): state the schema in
                # the prompt and parse the JSON out of the reply. Remembered per model for this process.
                _NO_SCHEMA.add(model)
                r = post(_with_schema_prompt(messages, schema), use_schema=False)
        r.raise_for_status()
        data = r.json()
        if "choices" not in data:   # OpenRouter reports provider/rate-limit errors in a 200 body
            raise LLMUnavailable(str(data.get("error") or data)[:300])
        msg = data["choices"][0]["message"]
        content = msg.get("content") or ""
        parsed = None
        if schema:
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                m = re.search(r"\{.*\}|\[.*\]", content, re.S)
                parsed = json.loads(m.group(0)) if m else None
        return {"content": content, "tool_calls": msg.get("tool_calls") or [], "json": parsed}

    return _cached("complete", payload, call)


# embeddings

def _local_embed(text: str, dim: int) -> list[float]:
    """Deterministic hashed embedding: word unigrams, bigrams and char trigrams, L2-normalised."""
    t = text.lower()
    toks = _TOKEN.findall(t)
    feats = toks + [a + "_" + b for a, b in zip(toks, toks[1:])]
    for tok in toks:
        padded = f"#{tok}#"
        feats += [padded[i:i + 3] for i in range(len(padded) - 2)]
    v = [0.0] * dim
    for f in feats:
        h = int.from_bytes(hashlib.blake2b(f.encode(), digest_size=8).digest(), "little")
        v[h % dim] += 1.0 if (h >> 32) & 1 else -1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def embed(texts: list[str]) -> list[list[float]]:
    dim = settings.embed_dim
    if not embed_available():
        return [_local_embed(t, dim) for t in texts]
    out: list[list[float]] = []
    for i in range(0, len(texts), 64):
        batch = texts[i:i + 64]

        def call(batch=batch) -> list[list[float]]:
            r = _post_retry("https://openrouter.ai/api/v1/embeddings",
                            {"model": settings.embed_model, "input": batch, "dimensions": dim})
            r.raise_for_status()
            return [d["embedding"] for d in r.json()["data"]]

        out += _cached("embed", {"m": settings.embed_model, "d": dim, "b": batch}, call)
    return out


def embed_model_name() -> str:
    return settings.embed_model if embed_available() else "local-hash-v1"
