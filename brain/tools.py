"""Tool registry: ten read tools returning evidence packs (03 §1.1–§1.2). The in-app agent, the MCP
server and the eval runners all call `run_tool` on this one registry. Write tools live in
`brain/actions.py` and are registered here too."""
from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

from . import chain as chainmod
from . import ids, providers, registry, templates
from .config import MAX, settings
from .db import Graph
from .past_belief_cypher import past_belief_cypher
from .write_path import load_chain, now_ms


@dataclass
class Ctx:
    g: Graph
    now: int = field(default_factory=now_ms)
    as_of: int | None = None          # valid time V
    belief_at: int | None = None      # belief time T (None = now)
    user_id: str = ""
    session_id: str = ""
    actor: str = ""
    packs: dict[str, dict] = field(default_factory=dict)
    queries: list[dict] = field(default_factory=list)
    anonymous: bool = False

    @property
    def V(self) -> int:
        return self.as_of if self.as_of is not None else self.now

    @property
    def T(self) -> int:
        return self.belief_at if self.belief_at is not None else self.now

    def q(self, name: str, params: dict, timeout: int = 2000) -> list[dict]:
        n0 = len(self.g.log)
        rows = self.g.ro(templates.body(name), params, timeout=timeout, template=name)
        for lg in self.g.log[n0:]:
            self.queries.append({"template": name, "cypher": templates.body(name), "params": _short(params),
                                 "rows": lg.rows, "ms": round(lg.ms, 2), "hash": templates.digest(name)})
        return rows


def _short(p: dict) -> dict:
    return {k: (f"<{len(v)} floats>" if isinstance(v, list) and v and isinstance(v[0], float) else v)
            for k, v in p.items()}


# Evidence pack plumbing

class PackBuilder:
    def __init__(self, ctx: Ctx, tool: str, args: dict):
        self.ctx, self.tool, self.args = ctx, tool, args
        self.items: list[dict] = []

    def item(self, label: str, score: float, facts: list[dict], path: dict | None = None,
             spans: list[dict] | None = None, actions: list[dict] | None = None, rows: list | None = None,
             note: str = "") -> dict:
        it = {"item_id": f"i{len(self.items) + 1}", "label": label, "score": round(score, 4), "path": path,
              "facts": facts, "actions": actions or [], "spans": spans or [], "rows": rows, "note": note}
        self.items.append(it)
        return it

    def build(self) -> dict:
        pid = "pk_" + hashlib.sha256(f"{self.tool}{sorted(self.args.items())}{self.ctx.now}{len(self.ctx.packs)}"
                                     .encode()).hexdigest()[:12]
        pack = {"pack_id": pid, "tool": self.tool, "args": self.args, "as_of": self.ctx.V,
                "belief_at": self.ctx.belief_at, "items": self.items}
        self.ctx.packs[pid] = pack
        return pack


def evidence(ctx: Ctx, aids: list[str]) -> dict[str, list[dict]]:
    """The shared evidence fragment (03 §1.1): the only way any tool reaches EVIDENCED_BY."""
    if not aids:
        return {}
    rows = ctx.q("evidence_fragment", {"aids": sorted(set(aids)), "T": ctx.T})
    out = {r["aid"]: [dict(e) for e in r["evs"]] for r in rows}
    sids = sorted({e["span"] for evs in out.values() for e in evs})
    det = {d["id"]: d for d in ctx.q("span_details", {"sids": sids, "T": ctx.T})} if sids else {}
    for aid, evs in out.items():
        for e in evs:
            d = det.get(e["span"], {})
            revs = d.get("revs") or []
            src = next((r for r in revs if r["src"] == e["src"]), revs[0] if revs else {})
            e.update({"text": d.get("text", ""), "ts": d.get("ts"), "kind": d.get("kind"),
                      "source_id": src.get("src", e["src"]), "doc_key": src.get("doc_key"),
                      "uri": src.get("uri"), "title": src.get("title"), "char_start": src.get("cs"),
                      "char_end": src.get("ce"), "live": any(r["live"] for r in revs)})
    return out


def span_items(ev: dict[str, list[dict]]) -> list[dict]:
    spans: dict[str, dict] = {}
    for aid, evs in ev.items():
        for e in evs:
            s = spans.setdefault(e["span"], {
                "span_id": e["span"], "text": e["text"], "source_id": e["source_id"], "doc_key": e["doc_key"],
                "uri": e["uri"], "title": e["title"], "kind": e["kind"], "ts": e["ts"],
                "char_start": e["char_start"], "char_end": e["char_end"], "live": e["live"], "cites": [],
                "form": e["form"], "authority": e["authority"], "quote_start": e["qs"], "quote_end": e["qe"]})
            if aid not in s["cites"]:
                s["cites"].append(aid)
    return list(spans.values())


def assertions(ctx: Ctx, aids: list[str]) -> dict[str, dict]:
    if not aids:
        return {}
    rows = ctx.q("assertions_by_id", {"ids": sorted(set(aids))})
    return {r["assertion_id"]: r for r in rows}


def _records_for(ctx: Ctx, chain_id: str) -> tuple[list[chainmod.Record], dict]:
    pred_q, _, _ = chain_id[3:].partition(":")
    pred, _, qual = pred_q.partition("+")
    snap = load_chain(ctx.g, chain_id, pred, qual, "")
    return snap.records, snap.meta


def chain_view(ctx: Ctx, chain_id: str) -> dict:
    """Status of every assertion in a chain at belief time T, plus disputes (open/settled at T).
    Python reference engine (02 §6); at T = now this equals the stored current belief (I6)."""
    cache = ctx.packs.setdefault("_chains", {})
    key = (chain_id, ctx.T)
    if key in cache:
        return cache[key]
    recs, meta = _records_for(ctx, chain_id)
    state = chainmod.walk(recs, ctx.T)
    by_id = {r.id: r for r in recs}
    disputes: dict[str, list[dict]] = defaultdict(list)    # run_id -> [{assertion_id, settled, confirmed_at}]
    for run in state.runs:
        for d in chainmod.disputes_against(state, run, recs, ctx.T):
            disputes[run.run_id].append(d)
    view = {"state": state, "by_id": by_id, "meta": meta, "disputes": disputes,
            "run_of": {m: run for run in state.runs for m in run.members}}
    if settings.past_belief_engine == "cypher" and ctx.belief_at is not None:
        _overlay_cypher_run(ctx, chain_id, view)
    cache[key] = view
    return view


def _overlay_cypher_run(ctx: Ctx, chain_id: str, view: dict) -> None:
    """PAST_BELIEF_ENGINE=cypher (02 §6, A38): the run containing V is taken from the Cypher engine;
    on any failure the Python view computed above stands (the reference is always the fallback)."""
    try:
        res = past_belief_cypher(ctx.g, chain_id, ctx.T, ctx.V)
    except Exception:  # noqa: BLE001 - version-specific shape, timeout, chain over the cap (I11)
        view["engine"] = "python"
        return
    view["engine"] = "cypher"
    view["cypher"] = res
    if res is None:
        return
    state = view["state"]
    for run in state.runs:
        if run.valid_from <= ctx.V < run.valid_to:
            run.members = [m for m in run.members if m in res["run"]] + \
                          [m for m in res["run"] if m not in run.members]
            run.valid_from, run.valid_to = res["valid_from"], res["valid_to"]
            for m in res["run"]:
                state.status[m] = res["states"][m]
                state.valid_to[m] = res["valid_to"]
                state.run_id[m] = run.run_id
                view["run_of"][m] = run
            view["disputes"][run.run_id] = res["disputes"]
            return


def facts(ctx: Ctx, aids: list[str], with_disputes: bool = True) -> list[dict]:
    """Pack facts with status evaluated at belief_at (A61) and D5 open disputes."""
    aids = list(dict.fromkeys(aids))
    stored = assertions(ctx, aids)
    out = []
    for aid in aids:
        a = stored.get(aid)
        if not a:
            continue
        f = {k: a[k] for k in ("assertion_id", "run_id", "predicate", "qualifier", "subject_id", "object_id",
                               "object_value", "negated", "valid_from", "valid_to", "status", "authority",
                               "statement")}
        f["open_disputes"] = []
        view = chain_view(ctx, a["chain_id"])
        st = view["state"]
        if aid in st.status:
            f["status"] = st.status[aid]
            f["valid_to"] = st.valid_to[aid]
            f["run_id"] = st.run_id[aid]
            f["authority"] = st.authority[aid]
        elif a["retracted_at"] <= ctx.T or a["recorded_at"] > ctx.T:
            f["status"] = "retracted" if a["recorded_at"] <= ctx.T else "unknown_at_T"
        if f["status"] == "proposed" or (f["status"] == "retracted" and a["authority"] == 0):
            links = ctx.q("proposal_links", {"ids": [aid], "now": ctx.T})
            if links:
                f["action_id"] = (links[0]["producers"] or [""])[0]
                if links[0]["confirmed_by"]:
                    f["confirmed_by"] = {"assertion_id": links[0]["confirmed_by"][0]}
        p = registry.get(a["predicate"], a["qualifier"] or "")
        run = view["run_of"].get(aid)
        if with_disputes and p.functional and f["status"] == "current" and run:
            f["open_disputes"] = [d["assertion_id"] for d in view["disputes"].get(run.run_id, []) if not d["settled"]]
        if f["status"] == "disputed":
            for rid, ds in view["disputes"].items():
                for d in ds:
                    if d["assertion_id"] == aid and d["settled"]:
                        f["overruled_by"] = {"confirmed_at": d["confirmed_at"], "run_id": rid}
        out.append(f)
    return out


def fact_item(ctx: Ctx, pb: PackBuilder, aids: list[str], path: dict | None = None, score: float = 1.0,
              label: str = "graph", note: str = "", extra_disputes: bool = True) -> dict | None:
    fs = facts(ctx, aids)
    if not fs:
        return None
    dispute_ids = sorted({d for f in fs for d in f["open_disputes"]})
    ev = evidence(ctx, [f["assertion_id"] for f in fs] + dispute_ids)
    it = pb.item(label, score, fs, path, span_items({a: e for a, e in ev.items() if a in aids}), note=note)
    acts = sorted({f["action_id"] for f in fs if f.get("action_id")})
    if acts:
        it["actions"] = [action_summary(ctx, a) for a in acts]
    if extra_disputes and dispute_ids:   # open disputes are items in their own right (03 §1.1)
        dfs = facts(ctx, dispute_ids, with_disputes=False)
        pb.item("graph", score * 0.9, dfs, None, span_items({a: e for a, e in ev.items() if a in dispute_ids}),
                note="open dispute")
    return it


def action_summary(ctx: Ctx, action_id: str) -> dict:
    rows = ctx.q("action_read", {"id": action_id})
    if not rows:
        return {"action_id": action_id}
    r = rows[0]
    ac = r["action"]
    actor = ac.get("actor", "")
    name = ctx.q("person_name", {"id": actor})
    return {"action_id": action_id, "kind": ac.get("kind"), "status": ac.get("status"),
            "actor": {"id": actor, "name": name[0]["n"] if name else actor}, "recorded_at": ac.get("recorded_at"),
            "eligibility": ac.get("eligibility"), "summary": ac.get("summary"), "based_on": r["based_on"],
            "produced": r["produced"], "sources": r["sources"], "targets": r["targets"],
            "undone_at": ac.get("undone_at", MAX)}


def run_aids(ctx: Ctx, run_id: str) -> list[str]:
    return [r["id"] for r in ctx.q("run_members", {"run": run_id})] or [run_id]


def make_path(steps: list[tuple[dict, dict | None]]) -> dict:
    pid = ids.path_id([(n["id"], (e or {}).get("type", ""), (e or {}).get("aid", "")) for n, e in steps])
    return {"path_id": pid, "steps": [{"node": n, "edge": e} for n, e in steps]}


def _node(ctx: Ctx, eid: str, name: str | None = None) -> dict:
    if name is None:
        r = ctx.q("entity_name", {"id": eid})
        name = r[0]["n"] if r else eid
    return {"id": eid, "labels": [registry.label_of(eid)] if ":" in eid else [], "name": name}


# Read tools

def _sanitize(q: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", q)
    return " ".join(words)


def link_entities(ctx: Ctx, mentions: list[str], types: list[str] | None = None) -> dict:
    pb = PackBuilder(ctx, "link_entities", {"mentions": mentions, "types": types})
    for m in mentions:
        ranks: dict[str, list[int]] = defaultdict(list)
        names: dict[str, tuple[str, list]] = {}
        exact = ctx.q("link_exact", {"q": m.strip().lower()})
        for r in exact:
            names[r["id"]] = (r["name"], r["labels"])
        q = _sanitize(m)
        ft = ctx.q("link_fulltext", {"q": q}) if q else []
        for i, r in enumerate(ft):
            ranks[r["id"]].append(i)
            names.setdefault(r["id"], (r["name"], r["labels"]))
        vec = providers.embed([m])[0]
        vv = ctx.q("link_vector", {"k": 20, "vec": vec})
        for i, r in enumerate(vv):
            if r["score"] > 0.8:   # cosine distance; far hits are noise
                continue
            ranks[r["id"]].append(i)
            names.setdefault(r["id"], (r["name"], r["labels"]))
        scores = {eid: sum(1 / (60 + rk) for rk in rs) for eid, rs in ranks.items()}
        for r in exact:
            scores[r["id"]] = 1.0 + scores.get(r["id"], 0)
        cands = sorted(scores, key=lambda e: -scores[e])
        if types:
            cands = [c for c in cands if registry.label_of(c) in types]
        cands = cands[:5]
        ambiguous = len(cands) > 1 and scores[cands[1]] >= 0.9 * scores[cands[0]]
        rows = [{"mention": m, "entity_id": c, "name": names[c][0], "type": registry.label_of(c),
                 "score": round(scores[c], 4), "ambiguous": ambiguous} for c in cands]
        pb.item("graph" if rows else "text_only", rows[0]["score"] if rows else 0.0, [], None, [], rows=rows,
                note=f"candidates for '{m}'")
    return pb.build()


def get_owner(ctx: Ctx, entity_id: str, as_of: int | None = None) -> dict:
    if as_of is not None:
        ctx.as_of = as_of
    pb = PackBuilder(ctx, "get_owner", {"entity_id": entity_id, "as_of": ctx.V})
    if ctx.belief_at is not None:
        return _owner_past(ctx, pb, entity_id)
    V = ctx.V
    label = "graph"
    owners = ctx.q("owner_at", {"x": entity_id, "V": V})
    note = ""
    via = None
    if not owners and entity_id.startswith("system:"):
        owners = ctx.q("owner_inherited", {"x": entity_id, "V": V})
        note = "inherited" if owners else ""
        via = owners[0] if owners else None
    if not owners:
        owners = ctx.q("owner_previous", {"x": entity_id, "V": V})
        note = "previous" if owners else ""
    xnode = _node(ctx, entity_id)
    for o in owners:
        steps: list[tuple[dict, dict | None]] = [(xnode, None)]
        aids = run_aids(ctx, o["aid"])
        if via:
            steps.append((_node(ctx, via["via"], via["via_name"]),
                          {"type": "PART_OF", "aid": via["via_aid"], "valid_from": None, "valid_to": None}))
            aids += run_aids(ctx, via["via_aid"])
        steps.append((_node(ctx, o["owner"], o["name"]),
                      {"type": "OWNS", "aid": o["aid"], "valid_from": o["vf"], "valid_to": o["vt"]}))
        if o["owner"].startswith("team:"):
            for ld in ctx.q("lead_at", {"t": o["owner"], "V": V}):
                steps.append((_node(ctx, ld["lead"], ld["name"]),
                              {"type": "LEADS", "aid": ld["aid"], "valid_from": ld["vf"], "valid_to": ld["vt"]}))
                aids += run_aids(ctx, ld["aid"])
        fact_item(ctx, pb, aids, make_path(steps), 1.0, label, note)
    return pb.build()


def _owner_past(ctx: Ctx, pb: PackBuilder, entity_id: str) -> dict:
    """get_owner under a past belief: computed from Assertions, never projections (02 §6)."""
    cid = registry.chain_id("OWNS", "", "", entity_id)
    view = chain_view(ctx, cid)
    for run in view["state"].runs:
        if run.valid_from <= ctx.V < run.valid_to and not run.negated:
            owner = run.value_id.rsplit("|", 1)[0]
            path = make_path([(_node(ctx, entity_id), None),
                              (_node(ctx, owner), {"type": "OWNS", "aid": run.run_id, "valid_from": run.valid_from,
                                                    "valid_to": run.valid_to})])
            fact_item(ctx, pb, list(run.members), path, 1.0, "graph", "past belief")
    return pb.build()


def get_history(ctx: Ctx, entity_id: str, predicate: str, belief_at: int | None = None,
                current_only: bool = False) -> dict:
    """With current_only, only the run valid at V (with D5 disputes) — "who leads X now?"."""
    if belief_at is not None:
        ctx.belief_at = belief_at
    pb = PackBuilder(ctx, "get_history", {"entity_id": entity_id, "predicate": predicate, "belief_at": belief_at,
                                          "current_only": current_only})
    chains = ctx.q("chains_for_entity", {"e": entity_id, "p": predicate})
    for c in sorted({r["chain"] for r in chains}):
        recs, meta = _records_for(ctx, c)
        aids = [r.id for r in sorted(recs, key=lambda r: (r.valid_from, r.id))
                if r.recorded_at <= ctx.T]
        fs = facts(ctx, aids)
        fs = [f for f in fs if f["status"] not in ("retracted", "unknown_at_T")]
        if current_only:
            fs = [f for f in fs if f["status"] == "current" and not f["negated"]
                  and f["valid_from"] <= ctx.V < f["valid_to"]]
            if fs:
                fact_item(ctx, pb, [f["assertion_id"] for f in fs], None, 1.0, "graph", f"current {predicate}")
            continue
        if not fs:
            continue
        ev = evidence(ctx, [f["assertion_id"] for f in fs])
        it = pb.item("graph", 1.0, fs, None, span_items(ev), note=f"history of {c}")
        acts = sorted({f["action_id"] for f in fs if f.get("action_id")})
        it["actions"] = [action_summary(ctx, a) for a in acts]
    return pb.build()


def trace_decision(ctx: Ctx, decision_id: str | None = None, entity_id: str | None = None) -> dict:
    pb = PackBuilder(ctx, "trace_decision", {"decision_id": decision_id, "entity_id": entity_id})
    V = ctx.V
    ds = [decision_id] if decision_id else [r["id"] for r in ctx.q("decisions_affecting", {"x": entity_id, "V": V})]
    seen: set[str] = set()
    queue = list(ds)
    while queue:
        d = queue.pop(0)
        if d in seen or len(seen) > 8:
            continue
        seen.add(d)
        rows = ctx.q("decision_trace", {"d": d, "V": V, "T": ctx.T})
        if not rows:
            continue
        r = rows[0]
        aids: list[str] = []
        if r["status_aid"]:
            aids += run_aids(ctx, r["status_aid"])
        for x in r["deciders"] + r["affects"]:
            if x.get("aid"):
                aids += run_aids(ctx, x["aid"])
        repl = ctx.q("replaces_out", {"d": d, "V": V})
        for x in repl:
            aids += run_aids(ctx, x["aid"])
            queue.append(x["o"])
        for x in ctx.q("replaced_by", {"d": d, "V": V}):
            queue.append(x["id"])
        props = [p["id"] for p in ctx.q("proposals_about", {"e": d})]
        aids += props
        mot = [m for m in r["motivated"] if m.get("span")]
        is_live = bool(r["status"]) or any(f["status"] == "proposed" for f in facts(ctx, aids))
        it = fact_item(ctx, pb, sorted(set(aids)), make_path([(_node(ctx, d, r["name"]), None)]), 1.0, "graph",
                       f"{r['name']}: {r['title'] or ''}") if (aids and is_live) else None
        if mot:
            det = {x["id"]: x for x in ctx.q("span_details", {"sids": [m["span"] for m in mot], "T": ctx.T})}
            ms = []
            for m in mot:
                x = det.get(m["span"])
                if not x or x["kind"] == "draft" or x["role"] == "agent":
                    continue
                rv = (x["revs"] or [{}])[0]
                ms.append({"span_id": x["id"], "text": x["text"], "source_id": rv.get("src"),
                           "doc_key": rv.get("doc_key"), "uri": rv.get("uri"), "title": rv.get("title"),
                           "kind": x["kind"], "ts": x["ts"], "char_start": rv.get("cs"), "char_end": rv.get("ce"),
                           "live": any(v["live"] for v in x["revs"]), "cites": [], "form": "prose",
                           "authority": 2, "section": m["section"], "proposed": bool(m["action_id"])})
            if it:
                it["spans"] += ms
            else:
                pb.item("text_only", 0.8, [], None, ms, note=f"rationale of {d}")
        # pending/confirmed drafts point at the new decision through proposals' SUBJECT/OBJECT
        for p in props:
            for rr in ctx.q("proposal_ends", {"p": p}):
                for e in (rr["s"], rr["o"]):
                    if e and e.startswith("decision:") and e not in seen:
                        queue.append(e)
    return pb.build()


_WEIGHTS = {"OWNS": 3.0, "LEADS": 3.0, "DECIDED_BY": 2.0, "ASSIGNED_TO": 2.0, "WORKS_ON": 1.5, "authored": 1.0}


def find_experts(ctx: Ctx, entity_id: str, k: int = 5) -> dict:
    pb = PackBuilder(ctx, "find_experts", {"entity_id": entity_id, "as_of": ctx.V, "k": k})
    rows = ctx.q("experts_signals", {"x": entity_id, "V": ctx.V})
    if not rows:
        return pb.build()
    r = rows[0]
    per: dict[str, dict] = defaultdict(lambda: {"score": 0.0, "signals": [], "authored": 0})
    for key in ("authored", "direct", "leads", "tickets", "decided"):
        for s in r[key] or []:
            if not s or not s.get("person"):
                continue
            p = per[s["person"]]
            w = _WEIGHTS.get(s["kind"], 1.0)
            if s["kind"] == "authored":
                if p["authored"] >= 5:
                    continue
                p["authored"] += 1
            age_days = max(0, (ctx.V - (s.get("ts") or ctx.V)) / 86400000)
            p["score"] += w * math.exp(-age_days / 90)
            p["signals"].append(s)
    top = sorted(per.items(), key=lambda kv: -kv[1]["score"])[:k]
    for person, info in top:
        aids = sorted({s["ref"] for s in info["signals"] if s["kind"] != "authored" and s.get("ref")})
        run_ids = []
        for a in aids:
            run_ids += run_aids(ctx, a)
        span_ids = sorted({s["ref"] for s in info["signals"] if s["kind"] == "authored"})
        breakdown = defaultdict(int)
        for s in info["signals"]:
            breakdown[s["kind"]] += 1
        note = f"{person}: " + ", ".join(f"{k}×{v}" for k, v in sorted(breakdown.items()))
        if run_ids:
            it = fact_item(ctx, pb, run_ids, make_path([(_node(ctx, entity_id), None), (_node(ctx, person), None)]),
                           info["score"], "graph", note, extra_disputes=False)
        else:
            it = pb.item("text_only", info["score"], [], make_path([(_node(ctx, entity_id), None),
                                                                     (_node(ctx, person), None)]), [], note=note)
        if span_ids and it is not None:
            det = ctx.q("span_details", {"sids": span_ids[:5], "T": ctx.T})
            for x in det:
                if x["kind"] == "draft" or x["role"] == "agent":
                    continue
                rv = (x["revs"] or [{}])[0]
                it["spans"].append({"span_id": x["id"], "text": x["text"], "source_id": rv.get("src"),
                                    "doc_key": rv.get("doc_key"), "uri": rv.get("uri"), "title": rv.get("title"),
                                    "kind": x["kind"], "ts": x["ts"], "char_start": rv.get("cs"),
                                    "char_end": rv.get("ce"), "live": any(v["live"] for v in x["revs"]),
                                    "cites": [], "form": "", "authority": 0})
        if it is not None:
            it["expert"] = {"person_id": person, "score": round(info["score"], 3), "breakdown": dict(breakdown)}
    return pb.build()


def find_paths(ctx: Ctx, from_id: str, to_id: str | None = None, types: list[str] | None = None,
               max_hops: int = 3) -> dict:
    h = max(1, min(3, int(max_hops)))
    allowed = [t for t in (types or registry.PROJECTION_TYPES) if t in registry.PROJECTION_TYPES]
    pb = PackBuilder(ctx, "find_paths", {"from_id": from_id, "to_id": to_id, "types": allowed, "max_hops": h})
    V = ctx.V
    if to_id is None:
        return _impact(ctx, pb, from_id)
    rows = ctx.q("paths_between", {"a": from_id, "b": to_id, "V": V, "h": h, "types": allowed})
    weights = {"OWNS": 1.0, "LEADS": 1.0, "DEPENDS_ON": 0.9, "MEMBER_OF": 0.8, "PART_OF": 0.8}
    for r in rows:
        steps = [({"id": r["ns"][0]["id"], "labels": [registry.label_of(r["ns"][0]["id"])], "name": r["ns"][0]["name"]},
                  None)]
        aids = []
        w = 1.0
        for n, e in zip(r["ns"][1:], r["es"]):
            steps.append(({"id": n["id"], "labels": [registry.label_of(n["id"])], "name": n["name"]},
                          {"type": e["type"], "aid": e["aid"], "valid_from": e["vf"], "valid_to": e["vt"]}))
            aids += run_aids(ctx, e["aid"])
            w *= weights.get(e["type"], 0.7)
        hops = len(r["es"])
        fact_item(ctx, pb, aids, make_path(steps), w * 0.5 ** (hops - 1), "graph", f"{hops} hop(s)")
    return pb.build()


def _impact(ctx: Ctx, pb: PackBuilder, x: str) -> dict:
    """Impact mode (A73): what breaks if x goes down, and who do I tell?"""
    V = ctx.V
    targets = [{"id": x, "name": None, "hops": 0, "node_ids": [x], "aids": []}]
    targets += ctx.q("impact_dependents", {"x": x, "V": V})
    for t in targets:
        steps: list[tuple[dict, dict | None]] = []
        aids: list[str] = []
        node_ids = t["node_ids"]
        for i, nid in enumerate(node_ids):
            edge = None
            if i > 0:
                edge = {"type": "DEPENDS_ON", "aid": t["aids"][i - 1], "valid_from": None, "valid_to": None}
                aids += run_aids(ctx, t["aids"][i - 1])
            steps.append((_node(ctx, nid), edge))
        sid = node_ids[-1]
        owners = ctx.q("owner_at", {"x": sid, "V": V}) or (
            ctx.q("owner_inherited", {"x": sid, "V": V}) if sid.startswith("system:") else [])
        for o in owners[:1]:
            steps.append((_node(ctx, o["owner"], o["name"]), {"type": "OWNS", "aid": o["aid"],
                                                               "valid_from": o["vf"], "valid_to": o["vt"]}))
            aids += run_aids(ctx, o["aid"])
            if o["owner"].startswith("team:"):
                for ld in ctx.q("lead_at", {"t": o["owner"], "V": V})[:1]:
                    steps.append((_node(ctx, ld["lead"], ld["name"]),
                                  {"type": "LEADS", "aid": ld["aid"], "valid_from": ld["vf"], "valid_to": ld["vt"]}))
                    aids += run_aids(ctx, ld["aid"])
        if aids:
            fact_item(ctx, pb, aids, make_path(steps), 1.0 / (1 + t["hops"]), "graph",
                      "the system itself" if t["hops"] == 0 else f"depends on {x} in {t['hops']} hop(s)")
    return pb.build()


def search_spans(ctx: Ctx, query: str, kinds: list[str] | None = None, k: int = 10,
                 present_tense: bool = False) -> dict:
    pb = PackBuilder(ctx, "search_spans", {"query": query, "kinds": kinds, "k": k})
    vec = providers.embed([query])[0]
    vv = ctx.q("search_vector", {"k": 50, "vec": vec})
    keys = ids.identifier_keys(query)
    words = _sanitize(query)
    ftq = " | ".join(filter(None, [words.replace(" ", " | ") if words else "",
                                   " | ".join(f"@keys:{t}" for t in keys.split() if len(t) > 2)]))
    ft = ctx.q("search_fulltext", {"q": ftq}) if ftq else []
    ranks: dict[str, float] = defaultdict(float)
    for i, r in enumerate(vv):
        ranks[r["id"]] += 1 / (60 + i)
    for i, r in enumerate(ft):
        ranks[r["id"]] += 1 / (60 + i)
    meta = {r["id"]: r for r in vv + ft}
    cands = [s for s in sorted(ranks, key=lambda s: -ranks[s])
             if (meta[s].get("ts") or 0) <= ctx.V and meta[s].get("kind") != "draft"
             and (not kinds or meta[s].get("kind") in kinds)]
    det = {d["id"]: d for d in ctx.q("span_details", {"sids": cands[:k * 2], "T": ctx.T})} if cands else {}
    n = 0
    for sid in cands:
        d = det.get(sid)
        if not d or d["role"] == "agent":
            continue
        live = any(r["live"] for r in d["revs"])
        if present_tense and not live:
            continue
        rv = next((r for r in d["revs"] if r["live"]), (d["revs"] or [{}])[0])
        pb.item("text_only", ranks[sid], [], None, [{
            "span_id": sid, "text": d["text"], "source_id": rv.get("src"), "doc_key": rv.get("doc_key"),
            "uri": rv.get("uri"), "title": rv.get("title"), "kind": d["kind"], "ts": d["ts"],
            "char_start": rv.get("cs"), "char_end": rv.get("ce"), "live": live, "cites": [], "form": "",
            "authority": 0}])
        n += 1
        if n >= k:
            break
    return pb.build()


SCHEMA_CARD = """Labels: Entity (+Person|Team|Project|System|Decision|Ticket) {id,name,aliases}, Assertion {id,predicate,
subject_id,object_id,object_value,status,valid_from,valid_to,run_id}, Span {id,text,ts,kind}, Source {id,doc_key,kind,title}.
Projection edges between entities (each has aid, valid_from, valid_to): OWNS, LEADS, MEMBER_OF{primary}, WORKS_ON,
DEPENDS_ON, PART_OF, DECIDED_BY, AFFECTS, REPLACES, ASSIGNED_TO, ABOUT. Current: valid_to = 9007199254740991.
Rules: read-only, one statement, no id(), typed variable-length patterns with upper bound <= 3, never IS NULL on
valid_to, no labels inside pattern comprehensions. Return ids/aids so results can be cited."""


def query_graph(ctx: Ctx, question: str) -> dict:
    pb = PackBuilder(ctx, "query_graph", {"question": question})
    if not providers.llm_available():
        pb.item("unverified_path", 0.0, [], None, [], rows=[], note="query_graph needs an LLM; none configured")
        return pb.build()
    cypher = ""
    for attempt in range(2):
        res = providers.complete([{"role": "system", "content": "Write one FalkorDB Cypher read query. " + SCHEMA_CARD
                                   + " Reply with the query only."},
                                  {"role": "user", "content": question}])
        cypher = res["content"].strip().strip("`").removeprefix("cypher").strip()
        if not _single_read(cypher):
            continue
        cypher = re.sub(r"\s+LIMIT\s+\d+\s*$", "", cypher, flags=re.I) + " LIMIT 200"
        try:
            rows = ctx.g.ro(cypher, {}, timeout=5000, template="query_graph")
            ctx.queries.append({"template": "query_graph", "cypher": cypher, "params": {}, "rows": len(rows),
                                "ms": round(ctx.g.log[-1].ms, 2), "unverified": True})
            break
        except Exception:  # noqa: BLE001
            rows = None
    else:
        rows = None
    if rows is None:
        pb.item("unverified_path", 0.0, [], None, [], rows=[], note="query failed; abstain")
        return pb.build()
    aids = sorted({v for r in rows for v in r.values() if isinstance(v, str) and v.startswith("as_")})
    if aids:
        fact_item(ctx, pb, aids, None, 0.5, "unverified_path", "resolved from generated Cypher")
    pb.item("unverified_path", 0.4, [], None, [], rows=[{k: v for k, v in r.items()} for r in rows[:50]],
            note=cypher)
    return pb.build()


def _single_read(q: str) -> bool:
    up = q.upper()
    if ";" in q.strip().rstrip(";") or any(w in up for w in ("CREATE", "MERGE", "DELETE", "SET ", "REMOVE",
                                                               "DROP", "CALL DB.IDX.FULLTEXT.CREATE")):
        return False
    return up.lstrip().startswith(("MATCH", "OPTIONAL MATCH", "WITH", "UNWIND", "RETURN", "CALL DB.IDX"))


def explain_action(ctx: Ctx, action_id: str) -> dict:
    pb = PackBuilder(ctx, "explain_action", {"action_id": action_id})
    summary = action_summary(ctx, action_id)
    if "kind" not in summary:
        return pb.build()
    then_t = summary["recorded_at"]
    out: dict[str, Any] = {}
    for label, t in (("then", then_t), ("now", ctx.now)):
        sub = Ctx(ctx.g, now=ctx.now, as_of=t if label == "then" else ctx.now, belief_at=t, packs=ctx.packs,
                  queries=ctx.queries)
        out[label] = {"based_on": facts(sub, summary["based_on"]), "produced": facts(sub, summary["produced"])}
    confirms = ctx.q("confirms_of", {"ids": summary["produced"]})
    changed = []
    for f_then in out["then"]["based_on"]:
        f_now = next((f for f in out["now"]["based_on"] if f["assertion_id"] == f_then["assertion_id"]), None)
        if f_now and f_now["status"] != f_then["status"]:
            changed.append({"assertion_id": f_then["assertion_id"], "then": f_then["status"], "now": f_now["status"],
                            "statement": f_then["statement"]})
    it = fact_item(ctx, pb, summary["based_on"] + summary["produced"], None, 1.0, "graph",
                   f"{summary['kind']} by {summary['actor']['name']}", extra_disputes=False) \
        or pb.item("graph", 1.0, [], None, [])
    it["actions"] = [summary] + [action_summary(ctx, c["action"]) for c in confirms if c["action"]]
    it["then_now"] = out
    it["changed_since"] = changed
    it["confirms"] = confirms
    return pb.build()


def recall_session(ctx: Ctx, user_id: str, query: str, k: int = 10) -> dict:
    pb = PackBuilder(ctx, "recall_session", {"user_id": user_id, "query": query, "k": k})
    if ctx.anonymous:
        pb.item("text_only", 0.0, [], None, [], note="unavailable without the token (A47)")
        return pb.build()
    rows = ctx.q("session_spans", {"user": user_id})
    qv = providers.embed([query])[0]
    vecs = providers.embed([r["text"] for r in rows]) if rows else []
    scored = sorted(zip(rows, vecs), key=lambda rv: -sum(a * b for a, b in zip(qv, rv[1])))[:k]
    for r, v in scored:
        pb.item("text_only", sum(a * b for a, b in zip(qv, v)), [], None, [{
            "span_id": r["id"], "text": r["text"], "source_id": "", "doc_key": "", "uri": "", "title": "session",
            "kind": "chat_session", "ts": r["ts"], "char_start": 0, "char_end": len(r["text"]), "live": True,
            "cites": [], "form": "chat", "authority": 1}])
    acts = ctx.q("recent_actions", {"u": user_id})
    if acts:
        pb.item("graph", 0.5, [], None, [], actions=[action_summary(ctx, a["id"]) for a in acts],
                note="your recent actions")
    return pb.build()


# Registry

@dataclass
class Tool:
    name: str
    kind: str
    fn: Callable
    schema: dict
    description: str
    timeout: int = 2000


def _s(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required}


STR = {"type": "string"}
INT = {"type": "integer"}
REGISTRY: dict[str, Tool] = {}


def register(t: Tool) -> None:
    REGISTRY[t.name] = t


register(Tool("link_entities", "read", link_entities,
              _s({"mentions": {"type": "array", "items": STR}, "types": {"type": "array", "items": STR}}, ["mentions"]),
              "Resolve names or ids mentioned by the user to entity ids."))
register(Tool("get_owner", "read", get_owner, _s({"entity_id": STR, "as_of": INT}, ["entity_id"]),
              "Who owns a system or project at a valid time, with the owning team's lead and open disputes."))
register(Tool("get_history", "read", get_history,
              _s({"entity_id": STR, "predicate": STR, "belief_at": INT, "current_only": {"type": "boolean"}},
                 ["entity_id", "predicate"]),
              "Every assertion in an entity's chain for a predicate: current, historical, disputed, proposed."))
register(Tool("trace_decision", "read", trace_decision, _s({"decision_id": STR, "entity_id": STR}, []),
              "Why a decision was made: replacement chain, deciders, what it affects, motivating spans."))
register(Tool("find_experts", "read", find_experts, _s({"entity_id": STR, "k": INT}, ["entity_id"]),
              "Who knows about an entity, with a per-signal breakdown."))
register(Tool("find_paths", "read", find_paths,
              _s({"from_id": STR, "to_id": STR, "types": {"type": "array", "items": STR}, "max_hops": INT}, ["from_id"]),
              "Typed paths between two entities; without to_id, impact mode: what depends on from_id and who to tell."))
register(Tool("search_spans", "read", search_spans,
              _s({"query": STR, "kinds": {"type": "array", "items": STR}, "k": INT}, ["query"]),
              "Hybrid text search over source spans. Text-only evidence; use when no template fits."))
register(Tool("query_graph", "read", query_graph, _s({"question": STR}, ["question"]),
              "Last resort: read-only generated Cypher. Results are labelled unverified.", timeout=5000))
register(Tool("explain_action", "read", explain_action, _s({"action_id": STR}, ["action_id"]),
              "What an action relied on and produced, then versus now, and who confirmed."))
register(Tool("recall_session", "read", recall_session, _s({"user_id": STR, "query": STR, "k": INT}, ["user_id", "query"]),
              "The user's own earlier turns and recent actions."))


def run_tool(ctx: Ctx, name: str, args: dict) -> dict:
    t = REGISTRY[name]
    return t.fn(ctx, **args)


def tool_specs(kind: str | None = None) -> list[dict]:
    """OpenAI-style function specs for the agent and MCP."""
    return [{"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.schema}}
            for t in REGISTRY.values() if kind is None or t.kind == kind]
