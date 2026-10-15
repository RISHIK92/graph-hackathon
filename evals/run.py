"""Eval runner. `python -m evals.run --seeds 1 2 3 [--rebuild] [--layers retrieval answer]`

Writes evals/results/<git-sha>/<layer>-<variant>.jsonl and summary.md (06 §8). The rule-3 gate:
C and D beat A and A+R on multi-hop, ownership, decision-trace and stale-fact Recall@5 by more than
the run-to-run noise across seeds.
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import time
from collections import defaultdict
from pathlib import Path

from brain.config import ROOT
from brain.db import Graph

from .gold import World
from .answer import script_key
from .questions import Generator, label_of
from .retrieval import VARIANTS, Retriever, score

GATE_CATS = {"2": "multi-hop", "3": "ownership", "4": "decision trace", "5": "stale fact"}
# Retrieval runs on every question that the seed graph can answer. Scripted questions (4-pending, 7, 9:
# `setup_script` / `turns`) need state written on a scratch graph, so they run in the answer layer only.
CAT_NAMES = {"1": "single-hop", "2": "multi-hop", "3": "ownership", "4": "decision trace", "4-pending": "pending draft",
             "5": "stale fact", "6": "unanswerable", "7": "past belief", "8": "disputed", "9": "session memory",
             "10": "outside templates", "11": "graph algorithms"}


def sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip() or "working"
    except Exception:  # noqa: BLE001
        return "working"


def seed_graph(seed: int, rebuild: bool) -> Graph:
    from brain.cli import reset_seed
    g = Graph(name=f"eval_seed{seed}")
    exists = False
    try:
        exists = g.ro("MATCH (s:Source) RETURN count(s) AS n")[0]["n"] > 0
    except Exception:  # noqa: BLE001
        pass
    if rebuild or not exists:
        reset_seed(g, str(ROOT / "world" / "seeds" / str(seed)))
    return g


def mean(xs: list) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 3) if xs else None


def run_retrieval(seeds: list[int], rebuild: bool, out: Path, questions_only: bool = False) -> dict:
    table: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))   # var -> cat -> metric -> [per seed]
    for seed in seeds:
        g = seed_graph(seed, rebuild)
        world = World.load(ROOT / "world" / "seeds" / str(seed))
        qs = Generator(world, g, seed).build()
        (out / f"questions-seed{seed}.jsonl").write_text("\n".join(json.dumps(q) for q in qs))
        if questions_only:
            continue
        r = Retriever(g, now=int(time.time() * 1000), as_of=world.today)
        for v in VARIANTS:
            rows = []
            per: dict = defaultdict(lambda: defaultdict(list))
            for q in qs:
                if script_key(q):
                    continue
                items = r.run(v, q)
                m = score(items, q)
                rows.append({"seed": seed, "id": q["id"], "category": q["category"], "label": label_of(q),
                             "anchor": q["anchor"], **m})
                for k, x in m.items():
                    per[label_of(q)][k].append(x)
                    per[("no_anchor", label_of(q))][k].append(x if not q["anchor"] else None)
            with (out / f"retrieval-{v}.jsonl").open("a") as f:
                f.write("\n".join(json.dumps(x) for x in rows) + "\n")
            for cat, ms in per.items():
                for k, xs in ms.items():
                    table[v][cat][k].append(mean(xs))
    return table


def gate(table: dict) -> list[dict]:
    out = []
    for cat, name in GATE_CATS.items():
        def vals(v):
            return [x for x in table[v][cat]["recall@5"] if x is not None]
        base = max(statistics.mean(vals("A") or [0]), statistics.mean(vals("A+R") or [0]))
        noise = max([statistics.pstdev(vals(v)) for v in ("A", "A+R", "C", "D") if len(vals(v)) > 1] or [0.0])
        for v in ("C", "D"):
            m = statistics.mean(vals(v) or [0])
            out.append({"category": name, "variant": v, "recall@5": round(m, 3), "best_baseline": round(base, 3),
                        "margin": round(m - base, 3), "noise": round(noise, 3), "pass": m - base > noise})
    return out


def summary(table: dict, seeds: list[int], out: Path) -> str:
    lines = [f"# Eval summary ({out.name}, seeds {seeds})", "",
             "Retrieval layer, mean over seeds. Gold comes from the world declarations only. Scripted categories",
             "(4-pending, 7, 9) run only in the answer layer (`answer-summary.md`); 10 has no span gold.", ""]
    for metric in ("recall@5", "recall@10", "mrr", "fact_accuracy", "stale_leak", "dispute_surfacing", "path_coverage"):
        lines += [f"## {metric}", "", "| Category | " + " | ".join(VARIANTS) + " |",
                  "|---|" + "---|" * len(VARIANTS)]
        for cat, name in CAT_NAMES.items():
            cells = []
            for v in VARIANTS:
                xs = [x for x in table[v][cat][metric] if x is not None]
                cells.append(f"{statistics.mean(xs):.3f}" if xs else "—")
            if any(c != "—" for c in cells):
                lines.append(f"| {cat} {name} | " + " | ".join(cells) + " |")
        lines.append("")
    lines += ["## Recall@5 without anchor questions", "", "| Category | " + " | ".join(VARIANTS) + " |",
              "|---|" + "---|" * len(VARIANTS)]
    for cat, name in CAT_NAMES.items():
        cells = []
        for v in VARIANTS:
            xs = [x for x in table[v][("no_anchor", cat)]["recall@5"] if x is not None]
            cells.append(f"{statistics.mean(xs):.3f}" if xs else "—")
        lines.append(f"| {cat} {name} | " + " | ".join(cells) + " |")
    g = gate(table)
    lines += ["", "## Rule-3 gate (C and D vs best of A, A+R; Recall@5; margin must exceed seed noise)", "",
              "| Category | Variant | R@5 | Best baseline | Margin | Noise | Pass |", "|---|---|---|---|---|---|---|"]
    for r in g:
        lines.append(f"| {r['category']} | {r['variant']} | {r['recall@5']} | {r['best_baseline']} | {r['margin']} | "
                     f"{r['noise']} | {'yes' if r['pass'] else 'NO'} |")
    text = "\n".join(lines) + "\n"
    (out / "summary.md").write_text(text)
    return text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", nargs="+", type=int, default=[1, 2, 3])
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--questions-only", action="store_true", help="only (re)generate questions-seed<n>.jsonl")
    a = ap.parse_args()
    out = ROOT / "evals" / "results" / sha()
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("retrieval-*.jsonl"):
        f.unlink()
    table = run_retrieval(a.seeds, a.rebuild, out, a.questions_only)
    if a.questions_only:
        print(f"questions written to {out}")
        return
    print(summary(table, a.seeds, out))


if __name__ == "__main__":
    main()
