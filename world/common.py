"""Shared helpers for the synthetic world (05 §3): time, slugs, chain keys."""
from __future__ import annotations

import datetime as _dt
import re

from brain import registry

MAX = 9007199254740991
DAY = 86_400_000
UTC = _dt.timezone.utc


class GenerationError(Exception):
    """A generator check failed (05 §3.1). Generation must stop."""


def to_ms(x) -> int:
    """ISO date / datetime string, date, datetime or int -> epoch ms (UTC). None -> MAX."""
    if x is None:
        return MAX
    if isinstance(x, bool):
        raise TypeError("bool is not a time")
    if isinstance(x, int):
        return x
    if isinstance(x, _dt.datetime):
        dt = x if x.tzinfo else x.replace(tzinfo=UTC)
        return int(dt.timestamp() * 1000)
    if isinstance(x, _dt.date):
        return to_ms(_dt.datetime(x.year, x.month, x.day, tzinfo=UTC))
    s = str(x).strip()
    if "T" in s or " " in s:
        return to_ms(_dt.datetime.fromisoformat(s.replace(" ", "T")))
    return to_ms(_dt.date.fromisoformat(s))


def iso(ms: int) -> str:
    return _dt.datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%d")


def day_floor(ms: int) -> int:
    return ms - ms % DAY


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def chain_of(p: str, q: str, s: str, o: str) -> tuple[str, str, str]:
    """(predicate, qualifier, key). key = key entity for functional chains, `s>o` otherwise."""
    pr = registry.get(p, q)
    if pr.key_side == "object":
        return (p, q, o)
    if pr.key_side == "subject":
        return (p, q, s)
    return (p, q, f"{s}>{o}")


def value_of(p: str, q: str, s: str, o: str, v: str, neg: bool) -> str:
    """The chain value a statement asserts: the non-key entity, the literal, or polarity."""
    pr = registry.get(p, q)
    if pr.key_side == "object":
        return s
    if pr.key_side == "subject":
        return o or v
    return "-" if neg else "+"


def is_functional(p: str, q: str) -> bool:
    return registry.get(p, q).functional


def claim_chain(c: dict) -> tuple[str, str, str]:
    return chain_of(c["p"], c.get("q", ""), c["s"], c.get("o", ""))


def claim_value(c: dict) -> str:
    return value_of(c["p"], c.get("q", ""), c["s"], c.get("o", ""), c.get("v", ""), c.get("neg", False))


def word_re(term: str) -> re.Pattern:
    """Case-insensitive whole-term match; a hyphen counts as part of a word (so
    `Billing` does not match inside `Billing-v2`)."""
    return re.compile(r"(?<![\w-])" + re.escape(term) + r"(?![\w-])", re.IGNORECASE)
