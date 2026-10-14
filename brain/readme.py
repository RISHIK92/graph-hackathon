"""Generate the README's "Cypher the product depends on" section from template headers (07 §3, rule 10/12),
so the README can't drift from the code. `python -m brain.readme` rewrites the block between markers."""
from __future__ import annotations

import re

from . import templates
from .config import ROOT

START, END = "<!-- cypher:start -->", "<!-- cypher:end -->"


def section() -> str:
    out = []
    for name in templates.all_names():
        h = templates.header(name)
        out.append(f"#### `{name}`\n\n{h.get('purpose', '')}  \nIndexes: {h.get('indexes', '—')}. "
                   f"Golden: `{h.get('golden', '—')}`.\n\n```cypher\n{templates.body(name)}\n```\n")
    out.append("#### Write path (`brain/write_path.py: build_query`)\n\nEvery fact write is ONE query: a guard stage "
               "that looks up chain versions and relied-on assertions in a single leading `UNWIND`, evaluates every "
               "check as a list expression and aborts through the unique-constraint sentinel "
               "(`FOREACH (_ IN CASE WHEN ok THEN [] ELSE [1] END | CREATE (:GuardFail {id:'sentinel'}))`), then list "
               "stages chained by `WITH count(*)` (one row even for empty lists), and a final `RETURN true AS guard_ok` "
               "whose row and write counters the API checks.\n")
    return "\n".join(out)


def main() -> None:
    p = ROOT / "README.md"
    text = p.read_text()
    block = f"{START}\n{section()}\n{END}"
    text = re.sub(re.escape(START) + r".*?" + re.escape(END), block, text, flags=re.S)
    p.write_text(text)
    print(f"README Cypher section: {len(templates.all_names())} templates")


if __name__ == "__main__":
    main()
