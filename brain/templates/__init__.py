"""Cypher templates as `.cypher` files with a header block (07 §3). The README's Cypher section is
generated from these headers, so it can't drift from the code."""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

DIR = Path(__file__).parent


@lru_cache(maxsize=None)
def load(name: str) -> str:
    return (DIR / f"{name}.cypher").read_text()


def body(name: str) -> str:
    return "\n".join(line for line in load(name).splitlines() if not line.startswith("//")).strip()


def header(name: str) -> dict:
    out: dict[str, str] = {}
    for line in load(name).splitlines():
        if line.startswith("// ") and ":" in line:
            k, v = line[3:].split(":", 1)
            out[k.strip()] = v.strip()
    return out


def all_names() -> list[str]:
    return sorted(p.stem for p in DIR.glob("*.cypher"))


def digest(name: str) -> str:
    return hashlib.sha256(body(name).encode()).hexdigest()[:12]
