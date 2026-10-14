"""The Cypher past-belief engine (02 §6, README A38/A53).

`past_belief_cypher(g, chain_id, t, v)` returns the same complete structure as the Python reference
`brain.chain.past_belief` (value, negated, interval, run members, member states at T, disputes open or
settled at T, evidence live at T), but every membership decision is made in Cypher from the stored,
time-stamped SUPERSEDES / CONTINUES / DISPUTES / EVIDENCED_BY edges. The stored `run_id` and `status`
are never read. Python only assembles the rows into the result shape.

Two templates (brain/templates/past_belief_run.cypher, past_belief_members.cypher), both bounded at
*1..50 (the chain cap, I11). Parity with the reference is tested in tests/test_parity.py (I9).
"""
from __future__ import annotations

from . import registry, templates
from .config import MAX
from .db import Graph


def _chain_predicate(chain_id: str) -> registry.Predicate:
    pred_q, _, _ = chain_id[3:].partition(":")
    pred, _, qual = pred_q.partition("+")
    return registry.get(pred, qual)


def _value(p: registry.Predicate, row: dict) -> str:
    """Same encoding as the Python engine's Record.value (02 §2): object id, "=literal", or ""."""
    if not p.functional:
        return ""
    if p.key_side == "object":
        return row["subject_id"]
    return row["object_id"] or "=" + (row["object_value"] or "")


def past_belief_cypher(g: Graph, chain_id: str, t: int, v: int) -> dict | None:
    """What the brain believed at belief time t about valid time v, for one chain, computed in Cypher."""
    p = _chain_predicate(chain_id)
    rows = g.ro(templates.body("past_belief_run"), {"chain": chain_id, "T": t, "V": v},
                template="past_belief_run")
    if not rows:
        return None
    # Several survivors of one run are the same answer (02 §6); the earliest is the run's head.
    head = rows[0]
    members = sorted({head["id"], *(head["others"] or [])})
    for r in rows[1:]:
        if r["id"] not in members:
            raise ValueError(f"past_belief_cypher: survivors in different runs at T={t} V={v}: "
                             f"{head['id']} and {r['id']}")
    mrows = g.ro(templates.body("past_belief_members"), {"members": members, "T": t},
                 template="past_belief_members")
    by_id = {r["id"]: r for r in mrows}
    if set(by_id) != set(members):
        raise ValueError(f"past_belief_cypher: member rows {sorted(by_id)} != run {members}")

    valid_from = min(r["valid_from"] for r in mrows)
    sup = [vf for r in mrows for vf in (r["sup_vfs"] or [])]
    valid_to = min(sup) if sup else MAX
    is_open = valid_to == MAX
    states = {m: "current" if is_open else "superseded" for m in members}

    # Settled rule (A56): a member's live confirmation span ts is greater than the challenger's latest
    # authored rank >= 1 evidence ts. `confirmed_at` is the latest live confirmation ts on the run.
    conf_ts = [e["ts"] or 0 for r in mrows for e in (r["evs"] or []) if e["form"] == "confirmation"]
    conf_at = max(conf_ts) if conf_ts else None
    disputes = []
    for r in mrows:
        for c in r["challengers"] or []:
            settled = conf_at is not None and conf_at > (c["last_ts"] or 0)
            disputes.append({"assertion_id": c["id"], "target": r["id"], "settled": settled,
                             "confirmed_at": conf_at})
    disputes.sort(key=lambda d: (d["assertion_id"], d["target"]))

    evidence = {m: sorted(e["span"] for e in (by_id[m]["evs"] or [])) for m in members}
    return {
        "value": _value(p, head),
        "negated": bool(head["negated"]),
        "valid_from": valid_from,
        "valid_to": valid_to,
        "run": members,
        "states": states,
        "disputes": disputes,
        "evidence": evidence,
    }


__all__ = ["past_belief_cypher"]
