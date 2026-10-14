"""CLI: generate, check and render seeded worlds.

    python -m world.build --seeds 1 2 3            # writes world/seeds/<seed>/{world.yaml,render/}
    python -m world.build --seeds 1 --out /tmp/w   # elsewhere
    python -m world.build --seeds 1 --paraphrase   # LLM paraphrase, only if OPENROUTER_API_KEY is set

Deterministic: the same seed gives byte-identical output.
"""
from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path

import yaml

from world.generator import build_seed

HERE = Path(__file__).resolve().parent


class _Dumper(yaml.SafeDumper):
    def ignore_aliases(self, data):  # never emit &id/*id anchors
        return True


def dump_yaml(data) -> str:
    return yaml.dump(data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=4096, default_flow_style=False)


def dump_json(data) -> str:
    return json.dumps(data, indent=1, ensure_ascii=False) + "\n"


def write_seed(seed: int, out_root: Path, paraphrase: bool = False) -> dict:
    world, files, manifest = build_seed(seed, paraphrase=paraphrase)
    out = out_root / str(seed)
    render_dir = out / "render"
    if render_dir.exists():
        shutil.rmtree(render_dir)
    render_dir.mkdir(parents=True)
    (out / "world.yaml").write_text(dump_yaml(world))
    for rel, text in sorted(files.items()):
        p = render_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    (render_dir / "manifest.json").write_text(dump_json(manifest))
    return summary(world, manifest)


def summary(world: dict, manifest: dict) -> dict:
    kinds = Counter(d["kind"] for d in manifest["documents"])
    outcomes = Counter(c["expected_outcome"] for c in world["changes"])
    by_pred = Counter(c["predicate"] + ("+" + c["qualifier"] if c["qualifier"] else "") for c in world["changes"])
    dis_docs, dis_changes = Counter(), Counter()
    for d in manifest["documents"]:
        dis_docs.update(d["distractors"])
    for c in world["changes"]:
        dis_changes.update(t for t in c["tags"] if t not in ("anchor", "reorg"))
    dis = {k: {"docs": dis_docs[k], "changes": dis_changes[k]} for k in sorted(set(dis_docs) | set(dis_changes))}
    disputed = Counter((c["statements"] and max((s for s in c["statements"] if s["states"] == "to"),
                                                 key=lambda s: s["rank"])["form"], c["challenger_correct"])
                       for c in world["changes"] if c["expected_outcome"] == "disputed")
    return {
        "seed": world["seed"],
        "entities": {k: len(world[k]) for k in ("people", "teams", "projects", "systems", "decisions", "tickets")},
        "facts": len(world["facts"]),
        "documents": dict(sorted(kinds.items())),
        "files": len({d["path"].split("#")[0] for d in manifest["documents"]}),
        "sentences": sum(len(d["sentences"]) for d in manifest["documents"]),
        "changes": dict(sorted(outcomes.items())),
        "changes_by_predicate": dict(sorted(by_pred.items())),
        "disputed_cells": {f"{f}/{'correct' if c else 'wrong'}": n for (f, c), n in sorted(disputed.items())},
        "distractors": dis,
    }


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    ap.add_argument("--out", type=Path, default=HERE / "seeds")
    ap.add_argument("--paraphrase", action="store_true", help="LLM paraphrase (needs OPENROUTER_API_KEY)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    for seed in args.seeds:
        s = write_seed(seed, args.out, paraphrase=args.paraphrase)
        if not args.quiet:
            print(json.dumps(s, indent=1))


if __name__ == "__main__":
    main()
