"""Identity functions (01 §2). Every ID is content- or request-derived, never a counter."""
from __future__ import annotations

import hashlib
import re
import time
import unicodedata

SEP = "␟"  # ␟

_QUOTES = {"‘": "'", "’": "'", "‚": "'", "‛": "'",
           "“": '"', "”": '"', "„": '"', "‟": '"'}
_WS = re.compile(r"\s+")


def norm(text: str) -> str:
    """NFKC, straight quotes, whitespace runs collapsed, trimmed. Case preserved."""
    t = unicodedata.normalize("NFKC", text or "")
    for k, v in _QUOTES.items():
        t = t.replace(k, v)
    return _WS.sub(" ", t).strip()


def _h(*parts: object, n: int = 16) -> str:
    raw = SEP.join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:n]


def doc_key(kind: str, system: str, external_id: str) -> str:
    return f"{kind}:{system}:{external_id}"


def source_rev(updated_at: int, text: str) -> str:
    return _h(updated_at, norm(text), n=12)


def source_id(dkey: str, updated_at: int, text: str) -> str:
    return f"{dkey}@{source_rev(updated_at, text)}"


def confirmation_source_id(action_id: str) -> str:
    return "src_conf_" + _h(action_id)


def draft_source_id(action_id: str, n: int = 0) -> str:
    return "src_draft_" + _h(action_id, n)


def span_id(dkey: str, text: str, occurrence: int) -> str:
    return "sp_" + _h(dkey, norm(text), occurrence)


def value_of(object_id: str, object_value: str) -> str:
    return object_id if object_id else "=" + object_value


def assertion_id(predicate: str, subject_id: str, object_id: str, object_value: str,
                 qualifier: str, negated: bool, valid_from: int, generation: int) -> str:
    return "as_" + _h(predicate, subject_id, value_of(object_id, object_value), qualifier,
                      "1" if negated else "0", valid_from, generation)


def action_id(session_source_id: str | None, request_id: str, kind: str, n: int = 0) -> str:
    return "ac_" + _h(session_source_id or "-", request_id, kind, n)


def path_id(steps: list[tuple[str, str, str]]) -> str:
    return "pa_" + _h(*["|".join(s) for s in steps])


_KEY_PATTERNS = [re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")]


def identifier_keys(text: str, slugs: list[str] | None = None) -> str:
    """`RDS-42` -> `rds42 rds 42` (05 §2 step 3)."""
    out: list[str] = []
    for pat in _KEY_PATTERNS:
        for m in pat.finditer(text):
            tok = m.group(0).lower()
            parts = re.split(r"[-_]", tok)
            out.append("".join(parts))
            out.extend(parts)
    for slug in slugs or []:
        if re.search(r"(?<![\w-])" + re.escape(slug) + r"(?![\w-])", text, re.IGNORECASE):
            parts = re.split(r"[-_]", slug.lower())
            out.append("".join(parts))
            out.extend(parts)
    seen: list[str] = []
    for t in out:
        if t not in seen:
            seen.append(t)
    return " ".join(seen)


def now_ms() -> int:
    return int(time.time() * 1000)
