"""Integrity checks run after every ingestion (06 §1): I1, I2, I5, I7, I11 and the guard sentinel."""
from __future__ import annotations

from . import registry
from .chain import walk
from .config import MAX
from .db import Graph
from .write_path import load_chain


def check(g: Graph, deep: bool = True) -> dict:
    v: list[dict] = []
    s = g.q("integrity_sentinel")[0]["n"]
    if s != 1:
        v.append({"check": "sentinel", "detail": f"{s} GuardFail nodes"})
    # I1: at most one open run per chain, and its members are current
    rows = g.q("integrity_i1", timeout=10000)
    for r in rows:
        if len(r["runs"]) > 1:
            v.append({"check": "I1", "chain": r["c"], "detail": f"{len(r['runs'])} open runs"})
    # I5: every assertion has evidence
    rows = g.q("integrity_i5", timeout=10000)
    for r in rows:
        v.append({"check": "I5", "assertion": r["id"]})
    # I11: chain cap
    rows = g.q("integrity_i11", timeout=10000)
    for r in rows:
        v.append({"check": "I11", "chain": r["c"], "detail": f"{r['n']} assertions"})
    if deep:
        v += _i2_i7(g)
    return {"ok": not v, "violations": v}


def _i2_i7(g: Graph) -> list[dict]:
    """I2 (projections equal the recomputed runs) and I7 (stored authority = live evidence max), per chain."""
    out: list[dict] = []
    chains = g.q("integrity_chains", timeout=10000)
    now = MAX - 1
    for c in chains:
        snap = load_chain(g, c["id"], c["p"], c["q"] or "", c["k"])
        st = walk(snap.records, now)
        for r in snap.records:
            m = snap.meta[r.id]
            if r.retracted_at != MAX:
                continue
            if m["status"] != st.status[r.id]:
                out.append({"check": "I2", "chain": c["id"], "assertion": r.id,
                            "detail": f"stored {m['status']} != recomputed {st.status[r.id]}"})
            if m["auth"] != st.authority[r.id]:
                out.append({"check": "I7", "assertion": r.id, "detail": f"{m['auth']} != {st.authority[r.id]}"})
        p = registry.get(c["p"], c["q"] or "")
        if p.projection.startswith("property:"):
            continue
        want = {(run.run_id, run.valid_from, run.valid_to) for run in st.runs if not run.negated}
        # Stays inline: the projection type comes from the registry, and a type(e) = $t filter
        # would scan every edge once per chain.
        have = {(r["aid"], r["vf"], r["vt"]) for r in g.ro(
            f"MATCH ()-[e:{p.projection}]->() WHERE e.chain = $c RETURN e.aid AS aid, e.valid_from AS vf, "
            "e.valid_to AS vt", {"c": c["id"]}, template="integrity_i2")}
        if want != have:
            out.append({"check": "I2", "chain": c["id"], "detail": f"projection {sorted(have)} != runs {sorted(want)}"})
    return out


def rebuild_projections(g: Graph) -> int:
    """Drop and rebuild every chain's projection from Assertions (I2 tool). Returns chains rebuilt."""
    from .write_path import WritePath
    chains = g.q("integrity_chains", timeout=10000)
    wp = WritePath(g)
    n = 0
    for c in chains:
        plan = wp.new_plan()
        snap = load_chain(g, c["id"], c["p"], c["q"] or "", c["k"])
        plan.chains[c["id"]] = snap
        if snap.records:   # a no-change update forces the write, whose stage 6 rebuilds the projection
            plan.updates.append({"id": snap.records[0].id, **_cur(snap)})
        wp.execute(plan)
        n += 1
    return n


def _cur(snap) -> dict:
    m = snap.meta[snap.records[0].id]
    return {"status": m["status"], "valid_to": m["vt"], "run_id": m["run"], "authority": m["auth"],
            "retracted_at": m["rt"]}
