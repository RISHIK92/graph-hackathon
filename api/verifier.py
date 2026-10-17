"""Deterministic claim verifier V1–V10 (03 §4; V10 checks aggregate claims) and answer assembly (A61). No LLM."""
from __future__ import annotations

from dataclasses import dataclass, field

from brain.ids import norm


@dataclass
class Index:
    spans: dict[str, dict] = field(default_factory=dict)
    facts: dict[str, dict] = field(default_factory=dict)
    actions: dict[str, dict] = field(default_factory=dict)
    paths: dict[str, dict] = field(default_factory=dict)
    fact_spans: dict[str, set[str]] = field(default_factory=dict)   # assertion -> live evidence spans
    aggregates: dict[tuple[str, str], dict] = field(default_factory=dict)   # (pack, item) -> aggregate item


def index_packs(packs: dict[str, dict]) -> Index:
    ix = Index()
    for pid, pack in packs.items():
        if pid.startswith("_"):
            continue
        for it in pack["items"]:
            for f in it["facts"]:
                ix.facts.setdefault(f["assertion_id"], f)
            for s in it["spans"]:
                ix.spans.setdefault(s["span_id"], s)
                for a in s.get("cites", []):
                    ix.fact_spans.setdefault(a, set()).add(s["span_id"])
            for a in it.get("actions") or []:
                if a.get("action_id"):
                    ix.actions.setdefault(a["action_id"], a)
            if it.get("path"):
                ix.paths.setdefault(it["path"]["path_id"], it["path"])
            if it.get("aggregate"):
                ix.aggregates[(pid, it["item_id"])] = it
            for side in ("then", "now"):
                for grp in ((it.get("then_now") or {}).get(side) or {}).values():
                    for f in grp:
                        ix.facts.setdefault(f["assertion_id"], f)
    return ix


def _fact_matches(claim_fact: dict, f: dict) -> bool:
    if not isinstance(claim_fact, dict):   # LLM drafts sometimes return the statement string here
        return False
    return (claim_fact.get("subject_id") == f["subject_id"] and claim_fact.get("predicate") == f["predicate"]
            and (claim_fact.get("object_id") or "") == (f.get("object_id") or "")
            and (claim_fact.get("object_value") or "") == (f.get("object_value") or "")
            and bool(claim_fact.get("negated")) == bool(f.get("negated")))


def _draft_or_agent(s: dict) -> bool:
    return s.get("kind") == "draft" or s.get("author_role") == "agent" or s.get("role") == "agent"


def verify(answer: dict, packs: dict[str, dict]) -> dict:
    ix = index_packs(packs)
    kept, dropped, rewritten = [], [], []
    claims = answer.get("claims") or []
    for c in claims:
        why = _check(c, ix, rewritten)
        if why:
            dropped.append({"claim_id": c["claim_id"], "rule": why[0], "detail": why[1]})
        else:
            kept.append(c)
    # V5 (answer level): a disputed claim needs a claim about the current fact of that chain.
    for c in list(kept):
        if c.get("label") != "graph":
            continue
        cited = [ix.facts[a] for a in c.get("assertion_ids", []) if a in ix.facts]
        disputed = [f for f in cited if f["status"] == "disputed"]
        if disputed and not any(f["status"] == "current" for f in cited) and c.get("tense") != "historical":
            if not c.get("disputed"):
                kept.remove(c)
                dropped.append({"claim_id": c["claim_id"], "rule": "V5", "detail": "disputed fact not flagged"})
                continue
            preds = {f["predicate"] for f in disputed}
            has_current = any(
                k is not c and any(ix.facts.get(a, {}).get("status") == "current"
                                   and ix.facts[a]["predicate"] in preds for a in k.get("assertion_ids", []))
                for k in kept)
            if not has_current:
                kept.remove(c)
                dropped.append({"claim_id": c["claim_id"], "rule": "V5", "detail": "no claim about the current fact"})
    abstained = not kept or len(dropped) > len(claims) / 2
    return {"kept": kept, "dropped": dropped, "rewritten": rewritten, "abstained": abstained, "checks": _passed(kept)}


CHECK_NAMES = {"V1": "Cited in this answer's evidence", "V2": "Matches the stored fact", "V3": "Quote found in a live source",
               "V4": "True at the date asked", "V7": "Open disputes disclosed", "V8": "Proposals labelled as proposed",
               "V9": "No draft or agent text cited", "V10": "Count matches the cited facts"}


def _passed(kept: list[dict]) -> dict[str, int]:
    """How many kept claims passed each named check (the trace's verifier report)."""
    out: dict[str, int] = {}
    for c in kept:
        label, proposed = c.get("label", "graph"), c.get("tense") == "proposed"
        ids = ["V1", "V9"] + (["V10"] if label == "aggregate" else ["V3"] if label != "graph"
                              else ["V8"] if proposed else ["V2", "V3", "V4", "V7"])
        for v in ids:
            out[CHECK_NAMES[v]] = out.get(CHECK_NAMES[v], 0) + 1
    return out


def _check(c: dict, ix: Index, rewritten: list) -> tuple[str, str] | None:
    # V1 membership
    for sid in c.get("span_ids", []):
        if sid not in ix.spans:
            return "V1", f"span {sid} not in this turn's packs"
    for a in c.get("assertion_ids", []):
        if a not in ix.facts:
            return "V1", f"assertion {a} not in packs"
    for a in c.get("action_ids", []):
        if a not in ix.actions:
            return "V1", f"action {a} not in packs"
    if c.get("path_id") and c["path_id"] not in ix.paths:
        return "V1", "path not in packs"
    # V9 draft / agent spans are never citable
    for sid in c.get("span_ids", []):
        if _draft_or_agent(ix.spans[sid]):
            return "V9", f"span {sid} is a draft or agent span"
    label = c.get("label", "graph")
    tense = c.get("tense", "current")
    cited = [ix.facts[a] for a in c.get("assertion_ids", [])]
    # V10 aggregate: the claim restates one aggregate item exactly (its count, every fact it used, all current)
    if label == "aggregate":
        it = ix.aggregates.get((c.get("pack_id", ""), c.get("item_id", "")))
        if not it:
            return "V10", "aggregate claim names no aggregate item in the packs"
        if c.get("count") != it["aggregate"]["count"]:
            return "V10", f"count {c.get('count')} != item count {it['aggregate']['count']}"
        if set(c.get("assertion_ids", [])) != {f["assertion_id"] for f in it["facts"]}:
            return "V10", "aggregate claim must cite every fact of its item"
        if any(f["status"] != "current" for f in cited):
            return "V10", "aggregate over a fact that isn't current"
        return None
    # V8 proposed
    if any(f["status"] == "proposed" for f in cited) or tense == "proposed":
        if tense != "proposed":
            return "V8", "a proposed fact can't be stated as current"
        props = [f for f in cited if f["status"] == "proposed" and (not c.get("fact") or _fact_matches(c["fact"], f))]
        if not props or any(f["status"] != "proposed" for f in cited):
            return "V8", "proposed claim needs matching proposed assertions only"
        for f in props:
            if f.get("action_id") and f["action_id"] not in c.get("action_ids", []):
                return "V8", "must cite the Action that produced the proposal"
        return None
    if label in ("text_only", "unverified_path"):
        # V6: skip V2, V4, V7, V8 but keep V3 and V9
        if c.get("quote"):
            if not any(norm(c["quote"]) in norm(ix.spans[s]["text"]) for s in c.get("span_ids", [])):
                return "V3", "quote not found in cited spans"
            if tense == "current" and not any(ix.spans[s].get("live") for s in c.get("span_ids", [])):
                return "V3", "present-tense text claim needs a span live at belief_at"
        elif label == "text_only":
            return "V3", "text-only claim needs a quote"
        return None
    # graph claims: one witness assertion must satisfy V2, V3, V4, V7 together (A61)
    if not cited:
        return "V2", "graph claim cites no assertion"
    errors = []
    for w in cited:
        if c.get("fact") and not _fact_matches(c["fact"], w):
            errors.append(("V2", "fact does not match the witness"))
            continue
        ev = ix.fact_spans.get(w["assertion_id"], set())
        q = c.get("quote")
        if not q or not any(s in ev and norm(q) in norm(ix.spans[s]["text"]) for s in c.get("span_ids", [])):
            errors.append(("V3", "quote is not in a live evidence span of the witness"))
            continue
        if tense == "current":
            if w["status"] != "current":
                if w["status"] == "superseded":
                    rewritten.append({"claim_id": c["claim_id"], "from": "current", "to": "historical"})
                    c["tense"] = "historical"
                    return None
                if w["status"] == "disputed" and c.get("disputed"):
                    return None
                errors.append(("V4", f"witness is {w['status']}, not current"))
                continue
            if w.get("open_disputes"):
                if not c.get("disputed") or not set(w["open_disputes"]) & set(c.get("assertion_ids", [])):
                    errors.append(("V7", "current fact has an open dispute the claim doesn't cite"))
                    continue
        return None
    return errors[0] if errors else ("V2", "no witness")


# What a first sentence must say to answer each intent (M4); intents not listed only need the asked entity.
_LEAD_WORDS = {"ownership": (" owns ", " owned ", " leads ", " led ", " is assigned to ", " is a member of ", " is part of "),
               "expertise": ("Ask ",), "impact": ("would be affected",), "dependency": ("depend",),
               "critical": ("Most depended-on",), "key_people": ("connections run through",), "gaps": ("with no",),
               "path": ("is connected to",),
               "decision_trace": ("because", " is ", "pending", "proposal"), "history": (" on ", " until "),
               "action": ("Route ", "Recorded", " owns ")}


def check_lead(plan: dict, lead: str) -> bool:
    """M4: the lead sentence names an entity the question asked about and answers the asked intent."""
    if not lead:
        return True
    names = [m["text"] for m in plan.get("mentions") or [] if m.get("entity_id")]
    if names and not any(n.lower() in lead.lower() for n in names):
        return False
    words = _LEAD_WORDS.get(plan.get("intent", ""))
    return not words or any(w in lead for w in words)


def assemble(kept: list[dict], packs: dict[str, dict], explanation: str = "") -> dict:
    """The displayed answer is built from surviving claims, never shown from the drafter's prose (A61)."""
    ix = index_packs(packs)
    lines = []
    seen: dict[str, dict] = {}
    for c in kept:
        if c.get("label") == "aggregate":
            it = ix.aggregates[(c["pack_id"], c["item_id"])]
            lines.append({"claim_id": c["claim_id"], "text": it["aggregate"]["text"], "status": "current", "also": []})
        elif c.get("label") == "graph" and c.get("assertion_ids"):
            f = ix.facts[c["assertion_ids"][0]]
            txt = f["statement"]
            if c.get("tense") == "historical":
                txt += " (historical)"
            elif c.get("tense") == "proposed":
                txt += " (proposed, pending confirmation)"
            elif c.get("disputed"):
                txt += " (disputed)"
            key = f"{txt}|{_chip(c, f)}"
            if key in seen:      # same statement from several run members: one line, all citations
                seen[key]["also"].append(c["claim_id"])
                continue
            line = {"claim_id": c["claim_id"], "text": txt, "status": _chip(c, f), "also": []}
            seen[key] = line
            lines.append(line)
        else:
            ctx = c.get("context")
            lines.append({"claim_id": c["claim_id"], "text": (f"{ctx}: " if ctx else "") + f"“{c.get('quote', '')}”",
                          "status": c.get("tense", "current"), "also": []})
    return {"lines": lines, "explanation": explanation}


def _chip(c: dict, f: dict) -> str:
    if c.get("tense") == "proposed":
        return "proposed"
    if c.get("disputed") or f["status"] == "disputed":
        return "disputed"
    return "historical" if c.get("tense") == "historical" else "current"
