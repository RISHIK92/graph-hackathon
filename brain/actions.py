"""Write tools, graph authorisation, confirmation and undo (01 §4.2–§4.3, 02 §5, §8, 03 §1.3).

Every write here goes through `write_path` in ONE guarded query that also writes the Action.
Refusals and aborts are recorded as separate `refused` / `aborted` Action writes so attempts are
auditable.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from . import chain as chainmod
from . import ids, registry
from .config import MAX
from .db import Graph, GuardFailed, WriteMismatch
from .write_path import Candidate, Plan, ValidationError, WritePath, load_chain, now_ms, payload, validate


DAY = 86_400_000


class Refused(Exception):
    def __init__(self, reason: str, eligible: list[dict] | None = None, fallback_available: bool = False,
                 action_id: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.eligible = eligible or []
        self.fallback_available = fallback_available
        self.action_id = action_id

    def as_dict(self) -> dict:
        return {"refused": True, "reason": self.reason, "eligible": self.eligible,
                "fallback_available": self.fallback_available, "action_id": self.action_id}


@dataclass
class Actor:
    person_id: str
    via: str = "session_user"            # session_user | mcp_client
    client: str = ""
    session_source_id: str = ""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))


# Current-belief reads used by the rules (projection edges valid now, authority >= 2, A57)

class Belief:
    def __init__(self, g: Graph, now: int):
        self.g, self.now = g, now

    def _edges(self, name: str, params: dict) -> list[dict]:
        return self.g.q(name, {**params, "now": self.now})

    def lead_of(self, team: str) -> list[dict]:
        return self._edges("belief_lead_of", {"t": team})

    def owners_of(self, x: str) -> list[dict]:
        return self._edges("belief_owners_of", {"x": x})

    def parent_of(self, x: str) -> list[dict]:
        return self._edges("belief_parent_of", {"x": x})

    def primary_team(self, p: str) -> list[dict]:
        return self._edges("belief_primary_team", {"p": p})

    def out_edges(self, rel: str, x: str) -> list[dict]:
        return self._edges("belief_out_edges", {"x": x, "rel": rel})

    def all_leads(self) -> list[dict]:
        return self._edges("belief_all_leads", {})

    def name(self, eid: str) -> str:
        r = self.g.q("entity_name", {"id": eid})
        return r[0]["n"] if r else eid


@dataclass
class Path:
    person: str
    name: str
    rule: str
    hops: list[tuple[str, str, str]]     # (from entity, edge type, to entity) as read
    aids: list[str]                      # projection aids (run ids) on the path

    def as_dict(self, b: Belief) -> dict:
        txt = " ".join(f"{_short(a)} −{t}→ {_short(c)}" for a, t, c in self.hops) if self.hops else ""
        return {"person_id": self.person, "name": self.name, "rule": self.rule, "path": txt, "aids": self.aids,
                "path_id": ids.path_id([(a, t, c) for a, t, c in self.hops])}


def _short(eid: str) -> str:
    return eid.split(":", 1)[-1]


class Rules:
    """Confirmer rules (01 §4.2). Each returns the eligible persons, each with the path that makes them so."""

    def __init__(self, b: Belief):
        self.b = b

    def team_lead(self, t: str, rule: str = "team_lead") -> list[Path]:
        return [Path(r["person"], r["name"], rule, [(r["person"], "LEADS", t)], [r["aid"]]) for r in self.b.lead_of(t)]

    def owner_lead(self, x: str, depth: int = 0) -> list[Path]:
        out = []
        owners = self.b.owners_of(x)
        for o in owners:
            if o["owner"].startswith("person:"):
                out.append(Path(o["owner"], o["name"], "owner_lead", [(o["owner"], "OWNS", x)], [o["aid"]]))
            else:
                for p in self.team_lead(o["owner"], "owner_lead"):
                    out.append(Path(p.person, p.name, "owner_lead", [(o["owner"], "OWNS", x)] + p.hops,
                                    [o["aid"]] + p.aids))
        if not owners and depth == 0:
            for par in self.b.parent_of(x):
                for p in self.owner_lead(par["parent"], 1):
                    out.append(Path(p.person, p.name, "owner_lead", [(x, "PART_OF", par["parent"])] + p.hops,
                                    [par["aid"]] + p.aids))
        return out

    def team_lead_primary(self, person: str) -> list[Path]:
        out = []
        for t in self.b.primary_team(person):
            for p in self.team_lead(t["team"], "team_lead(primary_team)"):
                out.append(Path(p.person, p.name, p.rule, [(person, "MEMBER_OF", t["team"])] + p.hops,
                                [t["aid"]] + p.aids))
        return out

    def deciders(self, d: str) -> list[Path]:
        out = []
        for w in self.b.out_edges("DECIDED_BY", d):
            if w["id"].startswith("person:"):
                out.append(Path(w["id"], w["name"], "deciders", [(d, "DECIDED_BY", w["id"])], [w["aid"]]))
            else:
                for p in self.team_lead(w["id"], "deciders"):
                    out.append(Path(p.person, p.name, "deciders", [(d, "DECIDED_BY", w["id"])] + p.hops,
                                    [w["aid"]] + p.aids))
        return out

    def replaced(self, d: str, draft_replaces: list[str] | None = None) -> list[str]:
        return [r["id"] for r in self.b.out_edges("REPLACES", d)] + (draft_replaces or [])

    def affects_leads(self, d: str, draft_affects: list[str] | None = None) -> list[Path]:
        out = []
        for x in [r["id"] for r in self.b.out_edges("AFFECTS", d)] + (draft_affects or []):
            out += self.owner_lead(x)
        return out

    def ticket_leads(self, k: str) -> list[Path]:
        out = []
        for x in self.b.out_edges("ABOUT", k):
            for p in self.owner_lead(x["id"]):
                out.append(Path(p.person, p.name, "ticket_leads", [(k, "ABOUT", x["id"])] + p.hops,
                                [x["aid"]] + p.aids))
        return out

    def for_assertion(self, a: dict, draft: dict | None = None) -> list[Path]:
        """Evaluate the predicate's confirmer cell for one target assertion (OR-combined)."""
        pred, qual = a["predicate"], a.get("qualifier") or ""
        s, o, v = a["subject_id"], a.get("object_id") or "", a.get("object_value") or ""
        draft = draft or {}
        if pred == "OWNS":
            return self.owner_lead(o)
        if pred == "LEADS":
            return self.team_lead(o) if o.startswith("team:") else self.owner_lead(o)
        if pred == "MEMBER_OF":
            return self.team_lead_primary(s) if qual == "primary" else self.team_lead(o)
        if pred == "WORKS_ON":
            return self.owner_lead(o)
        if pred in ("DEPENDS_ON", "PART_OF"):
            return self.owner_lead(s)
        if pred in ("DECIDED_BY", "AFFECTS") or (pred == "HAS_STATUS" and v != "superseded"):
            rep = self.replaced(s, draft.get("replaces"))
            if rep:
                out = []
                for d in rep:
                    out += self.deciders(d)
                return out
            return self.affects_leads(s, draft.get("affects"))
        if pred == "HAS_STATUS":
            return self.deciders(s)
        if pred == "REPLACES":
            return self.deciders(o)
        if pred in ("ASSIGNED_TO", "HAS_STATE"):
            return self.ticket_leads(s)
        if pred == "ABOUT":
            return self.owner_lead(o)
        return []

    def fallback(self) -> list[Path]:
        return [Path(r["person"], r["name"], "fallback(any team lead)", [(r["person"], "LEADS", r["team"])], [r["aid"]])
                for r in self.b.all_leads()]


def _dedupe(paths: list[Path]) -> list[Path]:
    seen, out = set(), []
    for p in paths:
        if (p.person, tuple(p.aids)) not in seen:
            seen.add((p.person, tuple(p.aids)))
            out.append(p)
    return out


# Service

class Actions:
    def __init__(self, g: Graph, clock=now_ms):
        self.g = g
        self.clock = clock

    # helpers
    def _names(self) -> dict[str, str]:
        rows = self.g.q("entity_names", timeout=10000)
        return {r["id"]: r["n"] for r in rows}

    def _assertion(self, aid: str) -> dict | None:
        r = self.g.q("assertion", {"id": aid})
        return r[0] if r else None

    def _action(self, aid: str) -> dict | None:
        r = self.g.q("action", {"id": aid})
        return r[0]["ac"] if r else None

    def _produced(self, action_id: str) -> tuple[list[str], list[str]]:
        a = self.g.q("produced_assertions", {"id": action_id})
        s = self.g.q("produced_sources", {"id": action_id})
        return [r["id"] for r in a], [r["id"] for r in s]

    def _action_props(self, actor: Actor, kind: str, now: int, summary: str, n: int = 0, **extra) -> dict:
        aid = ids.action_id(actor.session_source_id or None, actor.request_id, kind, n)
        return {"id": aid, "kind": kind, "actor": actor.person_id, "via": actor.via, "client": actor.client,
                "recorded_at": now, "status": "done", "undone_at": MAX, "summary": summary,
                "payload": extra.pop("payload", "{}"), "eligibility": extra.pop("eligibility", ""), **extra}

    def _record(self, actor: Actor, kind: str, status: str, summary: str, body: dict, targets: list[str]) -> str:
        """Separate audit write for `refused` / `aborted` attempts (01 §3)."""
        now = self.clock()
        props = self._action_props(actor, kind, now, summary, n=99, payload=payload(body))
        props["status"] = status
        self.g.write("MERGE (ac:Action {id:$id}) ON CREATE SET ac += $p", {"id": props["id"], "p": props},
                     template="action_audit")
        if targets:
            self.g.write("MATCH (ac:Action {id:$id}) UNWIND $t AS x MATCH (e:Entity {id:x}) MERGE (ac)-[:TARGETS]->(e)",
                         {"id": props["id"], "t": targets}, template="action_audit_targets")
        return props["id"]

    def _draft_source(self, plan: Plan, action_id: str, title: str, texts: list[str], now: int,
                      author: str) -> tuple[str, list[str]]:
        sid = ids.draft_source_id(action_id)
        plan.new_sources.append({"id": sid, "doc_key": f"draft:brain:{action_id}", "kind": "draft", "system": "brain",
                                 "external_id": action_id, "title": title, "uri": f"/sources/{sid}", "created_at": now,
                                 "updated_at": now, "ingested_at": now, "is_latest": True, "status": "draft",
                                 "user_id": ""})
        spans, pos = [], 0
        occ: dict[str, int] = {}
        for i, t in enumerate(texts):
            n = ids.norm(t)
            sp = ids.span_id(f"draft:brain:{action_id}", t, occ.get(n, 0))
            occ[n] = occ.get(n, 0) + 1
            plan.new_spans.append({"id": sp, "doc_key": f"draft:brain:{action_id}", "text": t, "keys": "", "ts": now,
                                   "author_id": author, "author_role": "agent", "kind": "draft",
                                   "embed_model": "none", "source_id": sid, "char_start": pos,
                                   "char_end": pos + len(t), "ordinal": i})
            spans.append(sp)
            pos += len(t) + 2
        plan.produced_sources.append(sid)
        return sid, spans

    def _run(self, wp: WritePath, plan: Plan, actor: Actor, kind: str, targets: list[str]) -> dict:
        try:
            return wp.execute(plan)
        except (GuardFailed, WriteMismatch) as e:
            self._record(actor, kind, "aborted", f"{kind} aborted: {type(e).__name__}", {"error": str(e)}, targets)
            raise

    # eligibility
    def eligibility(self, targets: list[dict], draft: dict | None = None, now: int | None = None) -> dict:
        b = Belief(self.g, now or self.clock())
        r = Rules(b)
        per_target = []
        union: list[Path] = []
        for t in targets:
            paths = _dedupe(r.for_assertion(t, draft))
            per_target.append({"target": t["id"], "paths": paths})
            union += paths
        fallback = not any(pt["paths"] for pt in per_target)
        fb_paths = r.fallback() if fallback else []
        return {"per_target": per_target, "fallback": fallback, "fallback_paths": fb_paths, "belief": b,
                "eligible": [p.as_dict(b) for p in (_dedupe(union) if not fallback else fb_paths)]}

    def missing_fact(self, targets: list[dict]) -> str:
        t = targets[0]
        names = self._names()
        key = t.get("object_id") if t["predicate"] in ("OWNS", "LEADS", "WORKS_ON", "ABOUT") else t["subject_id"]
        return f"{names.get(key, key)} has no current holder with a lead (authority ≥ 2)"

    def _actor_paths(self, el: dict, actor: str) -> tuple[list[Path], str] | None:
        """All targets must admit the actor. Returns (paths used, eligibility kind) or None."""
        if el["fallback"]:
            ps = [p for p in el["fallback_paths"] if p.person == actor]
            return (ps[:1], "fallback") if ps else None
        used: list[Path] = []
        for pt in el["per_target"]:
            mine = [p for p in pt["paths"] if p.person == actor]
            if not pt["paths"]:
                continue
            if not mine:
                return None
            used.append(mine[0])
        return used, "holder"

    # admissibility (02 §8 step 1: one definition, re-checked by the guard via status) --
    def _live_confirmations(self, run_id: str, now: int) -> list[dict]:
        return self.g.q("live_confirmations", {"run": run_id, "now": now})

    def _open_disputes(self, a: dict, now: int) -> list[str]:
        snap = load_chain(self.g, a["chain_id"], a["predicate"], a.get("qualifier") or "", "")
        st = chainmod.walk(snap.records, now)
        run = next((r for r in st.runs if a["id"] in r.members), None)
        if not run:
            return []
        return [d["assertion_id"] for d in chainmod.disputes_against(st, run, snap.records, now) if not d["settled"]]

    def _confirmer_name(self, action_id: str) -> str:
        ac = self._action(action_id) or {}
        return Belief(self.g, 0).name(ac.get("actor", "")) if ac else "someone"

    def admissible(self, a: dict, now: int) -> str | None:
        """None when admissible, else the refusal reason."""
        st = a["status"]
        if st == "proposed":
            conf = self.g.q("already_confirmed", {"id": a["id"], "now": now})
            if conf:
                return f"already confirmed by {self._confirmer_name(conf[0]['ac'])} (action {conf[0]['ac']})"
            pred = registry.get(a["predicate"], a.get("qualifier") or "")
            value = a["subject_id"] if pred.key_side == "object" else (a.get("object_id") or "=" + (a.get("object_value") or ""))
            snap = load_chain(self.g, a["chain_id"], a["predicate"], a.get("qualifier") or "", "")
            for r in snap.records:
                if r.retracted_at == MAX and r.id != a["id"] and r.authority_at(now) >= 1 and \
                        (r.value or "") == (value if pred.functional else "") and r.valid_from // DAY == now // DAY:
                    return f"collides with fact {r.id}; confirm {r.id} instead"
            return None
        if st == "retracted":
            w = self.g.q("withdrawn_by", {"id": a["id"]})
            if w and w[0]["s"] == "undone":
                return f"withdrawn by the undo of Action {w[0]['ac']}"
            return "retracted"
        if st == "superseded":
            return "superseded: confirm the later fact instead"
        if st == "disputed":
            tgt = self.g.q("disputed_run", {"id": a["id"], "max": MAX})
            if tgt:
                live = self._live_confirmations(tgt[0]["run"], now)
                if live:
                    who = self._confirmer_name(live[0]["action_id"])
                    return (f"{who}'s confirmation is live on the run this disputes; "
                            "undo that confirmation first")
            return None
        if st == "current":
            opened = self._open_disputes(a, now)
            if not opened:
                live = self._live_confirmations(a["run_id"], now)
                if live:
                    return f"already confirmed by {self._confirmer_name(live[0]['action_id'])}"
                return "already current"
            return None
        return f"not confirmable in status {st}"

    # confirm_fact (02 §8)
    def confirm_preview(self, actor_id: str, assertion_id: str | None = None, action_id: str | None = None) -> dict:
        now = self.clock()
        targets, draft = self._targets(assertion_id, action_id)
        if not targets:
            return {"admissible": False, "refusal": "nothing to confirm", "eligible": [], "fallback": False,
                    "actor_eligible": False}
        for t in targets:
            why = self.admissible(t, now)
            if why:
                return {"admissible": False, "refusal": why, "eligible": [], "fallback": False, "actor_eligible": False}
        el = self.eligibility(targets, draft, now)
        mine = self._actor_paths(el, actor_id)
        return {"admissible": True, "refusal": None, "eligible": el["eligible"], "fallback": el["fallback"],
                "actor_eligible": mine is not None,
                "missing_fact": self.missing_fact(targets) if el["fallback"] else None}

    def _targets(self, assertion_id: str | None, action_id: str | None) -> tuple[list[dict], dict | None]:
        if assertion_id:
            a = self._assertion(assertion_id)
            return ([a] if a else []), None
        ac = self._action(action_id or "")
        if not ac:
            return [], None
        prod, _ = self._produced(action_id)
        targets = [self._assertion(p) for p in prod]
        targets = [t for t in targets if t]
        draft = None
        if ac.get("kind") == "draft_adr_supersession":
            draft = {"replaces": [t["object_id"] for t in targets if t["predicate"] == "REPLACES"],
                     "affects": [t["object_id"] for t in targets if t["predicate"] == "AFFECTS"],
                     "new_decision": next((t["subject_id"] for t in targets if t["predicate"] == "REPLACES"), "")}
        return targets, draft

    def confirm_fact(self, actor: Actor, assertion_id: str | None = None, action_id: str | None = None) -> dict:
        now = self.clock()
        targets, draft = self._targets(assertion_id, action_id)
        if not targets:
            raise Refused("nothing to confirm")
        ent_targets = sorted({t["subject_id"] for t in targets} | {t["object_id"] for t in targets if t["object_id"]})
        for t in targets:
            why = self.admissible(t, now)
            if why:
                rid = self._record(actor, "confirm_fact", "refused", why, {"reason": why}, ent_targets)
                raise Refused(why, action_id=rid)
        el = self.eligibility(targets, draft, now)
        mine = self._actor_paths(el, actor.person_id)
        if mine is None:
            reason = "not eligible to confirm"
            if el["fallback"]:
                reason = f"{self.missing_fact(targets)}; any team lead may confirm"
            rid = self._record(actor, "confirm_fact", "refused", reason,
                               {"eligible": el["eligible"], "reason": reason}, ent_targets)
            raise Refused(reason, el["eligible"], el["fallback"], rid)
        paths, elig = mine
        # receiver: the path runs through the value the confirmed fact gives (e.g. the routed-to team);
        # holder wins when they coincide (A67).
        if elig == "holder":
            values = {t.get("object_id") for t in targets if t["predicate"] in ("ASSIGNED_TO",)}
            holders = {h[0] for p in paths for h in p.hops}
            if values and any(v in {h[2] for p in paths for h in p.hops} | holders for v in values if v) and \
                    not any(h[1] == "OWNS" for p in paths for h in p.hops):
                elig = "receiver"
        names = self._names()
        wp = WritePath(self.g, self.clock, names)
        plan = wp.new_plan(now)
        props = self._action_props(actor, "confirm_fact", now,
                                   f"{names.get(actor.person_id, actor.person_id)} confirmed: "
                                   + "; ".join(t["statement"] for t in targets), eligibility=elig)
        acid = props["id"]
        csid = ids.confirmation_source_id(acid)
        text = f"{names.get(actor.person_id, actor.person_id)} confirmed: " + "; ".join(t["statement"] for t in targets)
        plan.new_sources.append({"id": csid, "doc_key": f"confirmation:brain:{acid}", "kind": "confirmation",
                                 "system": "brain", "external_id": acid, "title": "Confirmation", "uri": f"/sources/{csid}",
                                 "created_at": now, "updated_at": now, "ingested_at": now, "is_latest": True,
                                 "status": "active", "user_id": ""})
        span = ids.span_id(f"confirmation:brain:{acid}", text, 0)
        plan.new_spans.append({"id": span, "doc_key": f"confirmation:brain:{acid}", "text": text, "keys": "",
                               "ts": now, "author_id": actor.person_id, "author_role": "system",
                               "kind": "confirmation", "embed_model": "none", "source_id": csid, "char_start": 0,
                               "char_end": len(text), "ordinal": 0})
        plan.produced_sources.append(csid)
        for t in targets:
            plan.target_status.append({"id": t["id"], "status": t["status"]})
            base = dict(predicate=t["predicate"], subject_id=t["subject_id"], object_id=t["object_id"] or "",
                        object_value=t["object_value"] or "", qualifier=t["qualifier"] or "",
                        negated=bool(t["negated"]), span_id=span, quote_start=0, quote_end=len(text),
                        source_id=csid, form="confirmation", extractor="confirm_fact", action_id=acid)
            if t["status"] == "proposed":
                c = Candidate(valid_from=now, valid_from_basis="source_time", force_new=True, **base)
                out = wp.add_candidate(plan, c)
                plan.confirms.append({"from": out["assertion_id"], "to": t["id"]})
                plan.produced_assertions.append(out["assertion_id"])
            else:
                c = Candidate(valid_from=t["valid_from"], valid_from_basis="stated", **base)
                wp.add_candidate(plan, c)
        if draft and draft.get("new_decision"):   # the confirmer becomes a decider (A55)
            out = wp.add_candidate(plan, Candidate("DECIDED_BY", draft["new_decision"], actor.person_id,
                                                   valid_from=now, span_id=span, quote_end=len(text), source_id=csid,
                                                   form="confirmation", extractor="confirm_fact", action_id=acid,
                                                   force_new=True))
            plan.produced_assertions.append(out["assertion_id"])
        based = []
        for p in paths:
            for aid in p.aids:
                based.append(aid)
        plan.elig_on = sorted(set(self._strongest_members(based, now)))
        plan.based_on = []
        plan.action = props
        plan.targets = ent_targets
        plan.session_id = actor.session_source_id
        try:
            self._run(wp, plan, actor, "confirm_fact", ent_targets)
        except (GuardFailed, WriteMismatch):
            # re-run steps 1-2 to explain the abort (02 §8 step 5)
            for t in targets:
                fresh = self._assertion(t["id"])
                why = self.admissible(fresh, self.clock()) if fresh else "target vanished"
                if why:
                    raise Refused(why)
            el2 = self.eligibility(targets, draft)
            if self._actor_paths(el2, actor.person_id) is None:
                raise Refused("not eligible to confirm", el2["eligible"], el2["fallback"])
            raise
        return {"action_id": acid, "eligibility": elig, "confirmation_source": csid,
                "produced": plan.produced_assertions}

    def _strongest_members(self, run_ids: list[str], now: int) -> list[str]:
        """For the guard: one member per run that is current with authority >= 2 (A57)."""
        out = []
        for rid in run_ids:
            rows = self.g.q("strongest_member", {"r": rid})
            if rows and rows[0]["au"] >= 2:
                out.append(rows[0]["id"])
            elif rows:
                out.append(rows[0]["id"])
            else:
                out.append(rid)
        return out

    # undo_action (02 §5, 01 §4.3)
    def undo_preview(self, actor_id: str, action_id: str) -> dict:
        ac = self._action(action_id)
        if not ac:
            return {"allowed": False, "reason": "no such action", "undoers": []}
        if ac.get("status") != "done":
            return {"allowed": False, "reason": f"action is {ac.get('status')}", "undoers": []}
        if ac["kind"] == "undo_action":
            return {"allowed": False, "reason": "undoing an undo is not supported; repeat the original write (L3)",
                    "undoers": []}
        undoers = [{"person_id": ac["actor"], "name": Belief(self.g, 0).name(ac["actor"]), "rule": "actor", "path": ""}]
        if ac["kind"] == "confirm_fact":
            targets = self._confirmed_targets(action_id)
            if targets:
                el = self.eligibility(targets)
                undoers += el["eligible"]
        allowed = any(u["person_id"] == actor_id for u in undoers)
        return {"allowed": allowed, "undoers": undoers, "reason": None if allowed else "not eligible to undo"}

    def _confirmed_targets(self, action_id: str) -> list[dict]:
        rows = self.g.q("confirmed_targets", {"ac": action_id})
        out = []
        for r in rows:
            a = self._assertion(r["id"])
            if a and a["status"] != "retracted":
                out.append(a)
        conf = self.g.q("confirmed_proposals", {"ac": action_id})
        for r in conf:
            a = self._assertion(r["id"])
            if a:
                out.append(a)
        return out

    def undo_action(self, actor: Actor, action_id: str) -> dict:
        now = self.clock()
        ac = self._action(action_id)
        if not ac:
            raise Refused("no such action")
        prev = self.undo_preview(actor.person_id, action_id)
        targets = [r["id"] for r in self.g.q("action_targets", {"id": action_id})]
        if not prev["allowed"]:
            reason = prev.get("reason") or "not eligible to undo"
            rid = self._record(actor, "undo_action", "refused", reason, {"undoers": prev["undoers"]}, targets)
            raise Refused(reason, prev["undoers"], action_id=rid)
        names = self._names()
        wp = WritePath(self.g, self.clock, names)
        plan = wp.new_plan(now)
        prod_a, prod_s = self._produced(action_id)
        for aid in prod_a:
            a = self._assertion(aid)
            if a and a["retracted_at"] == MAX:
                wp.load_for_assertion(plan, aid)
                wp.retract(plan, aid)
        # evidence this action added to existing assertions (dedup learn_fact, confirmations, A62)
        added = self.g.q("action_evidence", {"ac": action_id, "max": MAX})
        for r in added:
            wp.load_for_assertion(plan, r["aid"])
            wp.remove_evidence(plan, r["aid"], span_id=r["sid"], action_id=action_id,
                               retract_if_empty=r["aid"] not in plan.retract)
        for sid in prod_s:   # tombstone drafts and confirmation sources
            plan.extra_updates.append({"label": "Source", "id": sid, "props": {"status": "deleted"}})
        confirmed_any = bool(self.g.q("any_confirmed", {"id": action_id, "now": now}))
        if ac["kind"] == "draft_adr_supersession" and not confirmed_any:
            dec = self.g.q("draft_decision", {"id": action_id})
            for d in dec:
                plan.motivated_remove.append({"decision": d["d"], "action_id": action_id})
        plan.extra_updates.append({"label": "Action", "id": action_id, "props": {"status": "undone", "undone_at": now}})
        props = self._action_props(actor, "undo_action", now, f"undo of {ac['kind']} {action_id}",
                                   payload=payload({"undone": action_id}),
                                   eligibility="" if prev["undoers"][0]["person_id"] == actor.person_id else "holder")
        plan.action = props
        plan.targets = targets
        plan.session_id = actor.session_source_id
        self._run(wp, plan, actor, "undo_action", targets)
        return {"action_id": props["id"], "undone": action_id}

    # route_to_owner (03 §1.3, A28, A66, A78)
    def route_to_owner(self, actor: Actor, ticket_id: str | None = None, question_entity: str | None = None) -> dict:
        now = self.clock()
        b = Belief(self.g, now)
        names = self._names()
        if not ticket_id:
            x = question_entity
            owners = b.owners_of(x) if x else []
            raise Refused("route_to_owner needs a ticket; read-only suggestion: "
                          + (f"{names.get(owners[0]['owner'])} owns {names.get(x)}" if owners else "no owner found"))
        about = b.out_edges("ABOUT", ticket_id)
        if not about:
            raise Refused(f"{names.get(ticket_id, ticket_id)} is not about any system or project")
        x = about[0]["id"]
        owners = b.owners_of(x)
        based_runs = [about[0]["aid"]]
        if not owners:
            for par in b.parent_of(x):
                owners = b.owners_of(par["parent"])
                based_runs.append(par["aid"])
        if not owners:
            raise Refused(f"{names.get(x, x)} has no current owner")
        owner = owners[0]
        based_runs.append(owner["aid"])
        target = owner["owner"]
        if owner["owner"].startswith("team:"):
            leads = b.lead_of(owner["owner"])
            if leads:
                target = leads[0]["person"]
                based_runs.append(leads[0]["aid"])
        wp = WritePath(self.g, self.clock, names)
        plan = wp.new_plan(now)
        props = self._action_props(actor, "route_to_owner", now,
                                   f"Proposed routing {names.get(ticket_id)} to {names.get(target, target)}")
        acid = props["id"]
        msg = (f"Hand-off: {names.get(ticket_id)} is about {names.get(x)}, which {names.get(owner['owner'])} owns. "
               f"Proposing {names.get(target, target)} as assignee.")
        _, spans = self._draft_source(plan, acid, f"Hand-off for {names.get(ticket_id)}", [msg], now, actor.person_id)
        out = wp.add_candidate(plan, Candidate("ASSIGNED_TO", ticket_id, target, valid_from=now,
                                               valid_from_basis="source_time", span_id=spans[0], quote_end=len(msg),
                                               source_id=plan.new_sources[0]["id"], form="draft",
                                               extractor="draft:route_to_owner", action_id=acid, force_new=True))
        plan.produced_assertions.append(out["assertion_id"])
        plan.based_on = self._strongest_members(based_runs, now)
        plan.action = props
        plan.targets = [ticket_id]
        plan.session_id = actor.session_source_id
        self._run(wp, plan, actor, "route_to_owner", [ticket_id])
        return {"action_id": acid, "proposal": out["assertion_id"], "target": target}

    # draft_adr_supersession (A16, A24, A55)
    def draft_adr_supersession(self, actor: Actor, decision_id: str, reason: str) -> dict:
        now = self.clock()
        b = Belief(self.g, now)
        names = self._names()
        status = self.g.q("decision_status", {"d": decision_id})
        if not status:
            raise Refused(f"no decision {decision_id}")
        affects = b.out_edges("AFFECTS", decision_id)
        rationale = self.g.q("rationale_spans", {"d": decision_id, "max": MAX})
        based_runs = [a["aid"] for a in affects] + ([status[0]["aid"]] if status[0]["aid"] else [])
        ev = self.g.q("based_on_spans", {"runs": based_runs, "max": MAX})
        real = sorted({r["id"] for r in rationale} | {r["id"] for r in ev})
        if not real:
            raise Refused("a draft needs at least one real rationale span (A55)")
        num = status[0]["n"]
        new_id = "decision:draft-" + ids._h(decision_id, now, actor.request_id)[:8]
        new_name = f"Draft superseding {num}"
        wp = WritePath(self.g, self.clock, {**names, new_id: new_name})
        plan = wp.new_plan(now)
        props = self._action_props(actor, "draft_adr_supersession", now, f"Drafted {new_name}: {reason}")
        acid = props["id"]
        plan.new_entities.append({"label": "Decision", "props": {
            "id": new_id, "name": new_name, "aliases": [new_name.lower()], "aliases_text": new_name.lower(),
            "description": reason, "number": "", "title": reason, "decided_at": now, "created_from": acid,
            "status": "", "status_aid": ""}})
        lines = [f"{new_name} is accepted.", f"{num} is superseded.", f"{new_name} replaces {num}."]
        lines += [f"{new_name} affects {a['name']}." for a in affects]
        lines.append(f"Context: {reason}")
        sid, spans = self._draft_source(plan, acid, f"Draft ADR: {reason}", lines, now, actor.person_id)
        cands = [Candidate("HAS_STATUS", new_id, object_value="accepted"),
                 Candidate("HAS_STATUS", decision_id, object_value="superseded"),
                 Candidate("REPLACES", new_id, decision_id)]
        cands += [Candidate("AFFECTS", new_id, a["id"]) for a in affects]
        for c, sp, line in zip(cands, spans, lines):
            c.valid_from, c.span_id, c.quote_end, c.source_id = now, sp, len(line), sid
            c.form, c.extractor, c.action_id, c.force_new = "draft", "draft:draft_adr_supersession", acid, True
            out = wp.add_candidate(plan, c)
            plan.produced_assertions.append(out["assertion_id"])
        for s in real[:5]:
            plan.motivated_by.append({"decision": new_id, "span": s, "section": "context", "action_id": acid})
        plan.based_on = self._strongest_members(based_runs, now)
        plan.action = props
        plan.targets = [decision_id]
        plan.session_id = actor.session_source_id
        self._run(wp, plan, actor, "draft_adr_supersession", [decision_id])
        return {"action_id": acid, "decision": new_id, "proposals": plan.produced_assertions}

    # flag_stale_docs (A45, A75)
    def stale_detection(self, entity_id: str | None = None) -> list[dict]:
        """Read-only detection: latest-revision spans still stating a fact whose run is no longer valid,
        or superseding a run with live confirmation evidence ("overrides a confirmation")."""
        rows = self.g.q("stale_detection", {"max": MAX, "e": entity_id or ""}, timeout=10000)
        rows += self.g.q("stale_override", {"max": MAX}, timeout=10000)
        return rows

    def flag_stale_docs(self, actor: Actor, entity_id: str | None = None) -> dict:
        now = self.clock()
        found = self.stale_detection(entity_id)
        if not found:
            return {"action_id": None, "flagged": []}
        names = self._names()
        wp = WritePath(self.g, self.clock, names)
        plan = wp.new_plan(now)
        props = self._action_props(actor, "flag_stale_docs", now, f"Flagged {len(found)} stale span(s)")
        acid = props["id"]
        texts, based = [], []
        for f in found[:20]:
            cur = self.g.q("current_in_chain", {"c": f["chain"]})
            fix = cur[0]["st"] if cur else "no current fact"
            texts.append(f"In '{f['title']}': \"{f['statement']}\" is {f['why']}. Suggested correction: {fix}.")
            if cur:
                based.append(cur[0]["id"])
        self._draft_source(plan, acid, "Stale document corrections", texts, now, actor.person_id)
        plan.based_on = sorted(set(based))
        plan.action = props
        plan.targets = sorted({f["s"] for f in found} | {f["o"] for f in found if f["o"]})
        plan.session_id = actor.session_source_id
        self._run(wp, plan, actor, "flag_stale_docs", plan.targets)
        return {"action_id": acid, "flagged": found}

    # learn_fact (A9, A54, A62)
    def learn_fact(self, actor: Actor, turn_span_id: str, extracted: dict, session_source_id: str) -> dict:
        now = self.clock()
        sp = self.g.q("turn_span", {"id": turn_span_id, "src": session_source_id})
        if not sp or sp[0]["role"] != "user":
            raise Refused("learn_fact needs a user-authored span from the current session")
        text = sp[0]["text"]
        ents = {r["id"]: {"name": r["n"], "aliases": r["a"] or []} for r in
                self.g.q("learn_ents", {"ids": [extracted["subject_id"], extracted.get("object_id", "")]})}
        names = self._names()
        wp = WritePath(self.g, self.clock, names)
        plan = wp.new_plan(now)
        props = self._action_props(actor, "learn_fact", now, f"Learned from chat: {text[:80]}")
        acid = props["id"]
        c = Candidate(extracted["predicate"], extracted["subject_id"], extracted.get("object_id", ""),
                      extracted.get("object_value", ""), extracted.get("qualifier", ""),
                      bool(extracted.get("negated")), extracted.get("valid_from") or sp[0]["ts"],
                      "stated" if extracted.get("valid_from") else "source_time", turn_span_id,
                      extracted.get("quote_start", 0), extracted.get("quote_end", len(text)), session_source_id,
                      "chat", 0.8, "chat:learn_fact", acid)
        try:
            validate(self.g, c, ents, text, learn_fact_session=session_source_id)
        except ValidationError as e:
            raise Refused(f"learn_fact refused: {e}") from e
        out = wp.add_candidate(plan, c)
        if out["outcome"] == "new":
            plan.produced_assertions.append(out["assertion_id"])
        plan.action = props
        plan.targets = [x for x in (c.subject_id, c.object_id) if x]
        plan.session_id = session_source_id
        self._run(wp, plan, actor, "learn_fact", plan.targets)
        st = self._assertion(out["assertion_id"]) or {}
        return {"action_id": acid, "assertion_id": out["assertion_id"], "outcome": out["outcome"],
                "status": st.get("status")}
