"""`brain` CLI: reset --seed, ingest, integrity, health, probes."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import yaml

from . import integrity, schema, snapshot
from .config import ROOT, settings
from .db import Graph

DEFAULT_SEED = ROOT / "world" / "seeds" / "1"


def reset_seed(g: Graph, seed_dir: str | None = None) -> dict:
    """Delete the graph, recreate schema, re-ingest the committed render (04 §1 /admin/reset)."""
    from ingest.pipeline import Ingestor
    from . import providers
    seed = Path(seed_dir) if seed_dir else DEFAULT_SEED
    t0 = time.time()
    h0, m0 = providers.CACHE_STATS["hits"], providers.CACHE_STATS["misses"]
    snapshot.drop_all(g)   # derived from the graph being replaced (item 17)
    g.delete()
    schema.configure_timeouts(g)
    schema.create(g)
    rep = Ingestor(g).ingest_render(seed / "render")
    world = yaml.safe_load((seed / "world.yaml").read_text()) if (seed / "world.yaml").exists() else {}
    g.write("MERGE (s:Source {id:'world_meta'}) SET s.kind = 'world_meta', s.demo_identity = $d, s.seed = $seed, "
            "s.today = $today", {"d": world.get("demo_identity", ""), "seed": str(seed),
                                 "today": (world.get("company") or {}).get("today", 0)}, template="world_meta")
    rep.write(ROOT / "evals" / "results" / "extraction-report.jsonl")
    hits = providers.CACHE_STATS["hits"] - h0
    misses = providers.CACHE_STATS["misses"] - m0
    return {"seed": str(seed), "seconds": round(time.time() - t0, 1), "counts": rep.counts(),
            "sources": rep.sources, "integrity": integrity.check(g, deep=False),
            "cache_hit_rate": round(hits / (hits + misses), 3) if hits + misses else None}


def main() -> None:
    ap = argparse.ArgumentParser(prog="brain")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("reset")
    r.add_argument("--seed", default=str(DEFAULT_SEED), help="seed directory (world/seeds/<n>)")
    r.add_argument("--graph", default=settings.graph)
    i = sub.add_parser("integrity")
    i.add_argument("--deep", action="store_true")
    u = sub.add_parser("ingest", help="ingest an uploaded file: .md/.txt, Slack .json or export .zip")
    u.add_argument("--file", required=True)
    u.add_argument("--graph", default=settings.graph)
    sub.add_parser("health")
    p = sub.add_parser("probes")
    p.add_argument("--ports", default="6391,6392")
    a = ap.parse_args()
    if a.cmd == "reset":
        print(json.dumps(reset_seed(Graph(name=a.graph), a.seed), indent=2, default=str))
    elif a.cmd == "integrity":
        print(json.dumps(integrity.check(Graph(), deep=a.deep), indent=2))
    elif a.cmd == "ingest":
        from ingest.pipeline import Ingestor
        path = Path(a.file)
        rep = Ingestor(Graph(name=a.graph)).ingest_upload(path.name, path.read_bytes())
        print(json.dumps({"counts": rep.counts(), "sources": rep.sources, "skipped": rep.skipped}, indent=2))
    elif a.cmd == "health":
        print(json.dumps(schema.health(Graph(), settings.pin), indent=2))
    elif a.cmd == "probes":
        from evals.probes import run_versions
        doc = json.dumps(run_versions([int(p) for p in a.ports.split(",")]), indent=2, default=str)
        out = Path("evals/results/probes.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(doc + "\n")
        print(doc)


if __name__ == "__main__":
    main()
