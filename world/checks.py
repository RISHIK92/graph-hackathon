"""Generator checks (05 §3.1, §3.4). Each check raises `GenerationError`; any failure fails
generation. These checks only validate what was declared — they never produce gold.

The rank-rule check is deliberately written independently of 02 §3: one comparison over the
declared statements' ranks and stated times.
"""
from __future__ import annotations

import re
from collections import defaultdict

from world.common import GenerationError, claim_chain, claim_value, iso, word_re

DISTRACTOR_TYPES = ["stale_doc", "edited_doc", "near_dup_name", "hyphen_id", "chat_contradiction",
                    "stale_resolved", "edit_below_record", "fallback_gap", "equal_date_dispute",
                    "stale_unresolved", "hedge", "restatement_trap", "negation"]
G4_EXCLUDED = {"chat_contradiction", "stale_unresolved", "edit_below_record", "equal_date_dispute", "hedge",
               "fallback_gap"}


def fail(msg: str) -> None:
    raise GenerationError(msg)


# rank rule

def rule_outcome(ch: dict) -> tuple[str, bool]:
    """(outcome by the rank rule, is_equal_date) for one declared change."""
    sts = ch["statements"]
    old = [s for s in sts if s["states"] == "from" and s["live"]]
    new = [s for s in sts if s["states"] == "to"]
    old_rank = max((s["rank"] for s in old), default=0)
    old_latest = max((s["stated_at"] for s in old), default=-1)
    resolved = any(s["rank"] >= old_rank and s["stated_at"] > old_latest for s in new)
    equal_date = bool(new) and min(s["stated_at"] for s in new) == old_latest
    return ("resolved" if resolved else "disputed"), equal_date


def check_rank_rule(changes: list[dict]) -> None:
    for ch in changes:
        cid = ch["change_id"]
        if ch["expected_outcome"] not in ("resolved", "disputed"):
            fail(f"{cid}: bad expected_outcome {ch['expected_outcome']!r}")
        if ch["to"] == "":
            # a deliberate gap: the old value's record statements were removed, nothing replaces them
            if "fallback_gap" not in ch["tags"]:
                fail(f"{cid}: a chain left without a value must be tagged fallback_gap")
            if ch["expected_outcome"] != "resolved":
                fail(f"{cid}: a fallback_gap closes the chain, so it is declared resolved")
            live = [s for s in ch["statements"] if s["states"] == "from" and s["live"] and s["rank"] >= 2]
            if live:
                fail(f"{cid}: fallback_gap but {live[0]['doc_key']} still states the old value at rank {live[0]['rank']}")
            continue
        if not any(s["states"] == "to" for s in ch["statements"]):
            fail(f"{cid}: no rendered statement states the new value")
        outcome, equal_date = rule_outcome(ch)
        if outcome != ch["expected_outcome"]:
            fail(f"{cid}: declared {ch['expected_outcome']} but the rank rule gives {outcome}")
        tagged = "equal_date_dispute" in ch["tags"]
        if equal_date or tagged:
            old_rank = max((s["rank"] for s in ch["statements"] if s["states"] == "from" and s["live"]), default=0)
            to_rank = max(s["rank"] for s in ch["statements"] if s["states"] == "to")
            if not (equal_date and tagged):
                fail(f"{cid}: equal-date entry and equal_date_dispute tag disagree")
            if ch["expected_outcome"] != "disputed" or not to_rank < old_rank:
                fail(f"{cid}: equal-date entries must be disputed with the new value ranked strictly below")
        if ch["expected_outcome"] == "disputed":
            if ch["challenger_correct"] not in (True, False):
                fail(f"{cid}: disputed change needs challenger_correct")
            if ch["true"] != ch["challenger_correct"]:
                fail(f"{cid}: `true` must equal challenger_correct for a disputed change")
        elif ch["challenger_correct"] is not None:
            fail(f"{cid}: resolved change carries challenger_correct")


# stale docs

def latest_docs(manifest: dict) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for d in manifest["documents"]:
        if d["doc_key"] not in latest or d["updated_at"] > latest[d["doc_key"]]["updated_at"]:
            latest[d["doc_key"]] = d
    return latest


def check_stale_docs(changes: list[dict], manifest: dict) -> None:
    latest = latest_docs(manifest)
    for ch in changes:
        ref = "change:" + ch["change_id"]
        if ch["expected_outcome"] != "resolved":
            if ch["stale_docs"]:
                fail(f"{ch['change_id']}: only resolved changes list stale_docs")
            continue
        found = set()
        for dk, d in latest.items():
            states = {s["states"] for s in d["sentences"] if s["ref"] == ref}
            if "from" in states and "to" not in states:
                found.add(dk)
        if sorted(found) != sorted(ch["stale_docs"]):
            fail(f"{ch['change_id']}: stale_docs {sorted(ch['stale_docs'])} != manifest scan {sorted(found)}")


# declared gold

class DeclaredGold:
    """Chain state read from the declarations (05 §3.3): the earliest stated value, moved only
    by `resolved` changes. No rank logic."""

    def __init__(self, changes: list[dict], revs: list[dict]):
        self.resolved: dict[tuple, list[dict]] = defaultdict(list)
        self.all: dict[tuple, list[dict]] = defaultdict(list)
        for c in changes:
            ch = (c["predicate"], c["qualifier"], c["key"])
            self.all[ch].append(c)
            if c["expected_outcome"] == "resolved":
                self.resolved[ch].append(c)
        for lst in self.resolved.values():
            lst.sort(key=lambda c: c["at"])
        self.initial: dict[tuple, tuple] = {}
        for r in revs:
            for c in r["claims"]:
                ch = claim_chain(c)
                cand = (c["stated_at"], -c["rank"], claim_value(c))
                if ch not in self.initial or cand < self.initial[ch]:
                    self.initial[ch] = cand

    def value(self, chain: tuple, t: int) -> str | None:
        init = self.initial.get(chain)
        cur = init[2] if init and init[0] <= t else None
        for c in self.resolved.get(chain, []):
            if c["at"] <= t:
                cur = c["to"] or None
        return cur

    def walk(self, chain: tuple) -> list[tuple[int, str | None, dict | None]]:
        init = self.initial.get(chain)
        if not init:
            fail(f"chain {chain} has no statement at all")
        out = [(init[0], init[2], None)]
        cur = init[2]
        for c in self.resolved.get(chain, []):
            if c["from"] != cur:
                fail(f"{c['change_id']}: declared from {c['from']!r} but the chain holds {cur!r} before {iso(c['at'])}")
            cur = c["to"]
            out.append((c["at"], cur or None, c))
        return out


def check_consistency(changes: list[dict], gold: DeclaredGold) -> None:
    for chain in sorted(gold.all):
        gold.walk(chain)
    for c in changes:
        if c["expected_outcome"] == "disputed":
            ch = (c["predicate"], c["qualifier"], c["key"])
            if gold.value(ch, c["at"]) != c["from"]:
                fail(f"{c['change_id']}: disputed change's from {c['from']} is not the recorded value at {iso(c['at'])}")


def check_coverage(W, gold: DeclaredGold) -> None:
    start = W.company["start_date"]
    for eid in [s["id"] for s in W.systems] + [p["id"] for p in W.projects]:
        _covered(("OWNS", "", eid), gold, start, f"{eid} owner")
    for t in W.teams:
        _covered(("LEADS", "", t["id"]), gold, start, f"{t['id']} lead")


def _covered(chain: tuple, gold: DeclaredGold, start: int, what: str) -> None:
    steps = gold.walk(chain)
    if steps[0][0] > start:
        fail(f"coverage: {what} is first stated on {iso(steps[0][0])}, after the company start")
    for at, val, c in steps[1:]:
        if val is None and "fallback_gap" not in c["tags"]:
            fail(f"coverage: {what} is missing from {iso(at)} without a fallback_gap tag")


# balance

def challenger_form(ch: dict) -> str:
    to = [s for s in ch["statements"] if s["states"] == "to"]
    best = max(to, key=lambda s: s["rank"])
    return best["form"]


def check_balance(changes: list[dict]) -> dict:
    cells = {("chat", True): 0, ("chat", False): 0, ("prose", True): 0, ("prose", False): 0}
    for ch in changes:
        if ch["expected_outcome"] != "disputed":
            continue
        form = challenger_form(ch)
        if form not in ("chat", "prose"):
            fail(f"{ch['change_id']}: disputed challenger must be chat or prose, got {form}")
        cells[(form, ch["challenger_correct"])] += 1
    if len(set(cells.values())) != 1 or not cells[("chat", True)]:
        fail(f"balance: disputed cells must be equal and non-empty, got {cells}")
    return cells


# names

def check_names(W) -> None:
    from world.generator import PUBLIC_FIGURES

    seen: dict[str, str] = {}
    for e in W.entities():
        if e["id"].startswith("person:") and e["name"].lower() in PUBLIC_FIGURES:
            fail(f"{e['id']} is named after a public figure")
        for n in [e["name"]] + e["aliases"]:
            k = n.lower()
            if k in seen and seen[k] != e["id"]:
                fail(f"name/alias {n!r} used by both {seen[k]} and {e['id']}")
            seen[k] = e["id"]


# anchor G1-G12

def _mentions(W, eid: str, text: str) -> bool:
    e = W.ent(eid)
    return any(word_re(n).search(text) for n in [e["name"]] + e["aliases"])


def check_anchor(W, world: dict, manifest: dict, revs: list[dict], gold: DeclaredGold) -> None:
    A = W.anchor_ids
    ledger, payments, platform, infra = A["ledger"], A["payments"], A["platform"], A["infra"]
    changes = {c["change_id"]: c for c in world["changes"]}
    Dt, Dr = W.D_transfer, W.D_reorg
    today = W.company["today"]
    ledger_chain = ("OWNS", "", ledger)
    tickets = {t["id"]: t for t in W.tickets}

    # G1 catalogue, tickets, chat thread
    if not any(r["kind"] == "catalog" and any(c["o"] == ledger or c["s"] == ledger for c in r["claims"]) for r in revs):
        fail("G1: Ledger is not in the service catalogue")
    rds42, closed = tickets[A["rds42"]], tickets[A["closed_ledger_ticket"]]
    for t in (rds42, closed):
        if ledger not in [a["about"] for a in t["about_timeline"]]:
            fail(f"G1: {t['key']} has no Ledger component")
    if closed["state_timeline"][-1]["state"] != "done":
        fail("G1: the closed Ledger ticket is not done")
    threads: dict[tuple, list[dict]] = defaultdict(list)
    for d in W.docs:
        if d["kind"] == "chat":
            threads[(d["channel"], d.get("thread_ts") or d["ts"])].append(d)
    ok = False
    for (ch, root), msgs in threads.items():
        root_msg = [m for m in msgs if m["ts"] == root]
        text = " ".join(s["text"] for s in root_msg[0]["revisions"][0]["paragraphs"][0]) if root_msg else ""
        if len(msgs) >= 4 and _mentions(W, ledger, text):
            ok = True
    if not ok:
        fail("G1: no chat thread of >= 4 messages about Ledger")

    # G2 transfer
    c = changes.get(A["ledger_transfer_change"])
    if not c or (c["predicate"], c["key"], c["from"], c["to"], c["at"], c["expected_outcome"]) != \
            ("OWNS", ledger, platform, payments, Dt, "resolved"):
        fail("G2: the Ledger transfer change is missing or wrong")
    if c["stale_docs"] != [A["stale_wiki"]]:
        fail(f"G2: Ledger transfer stale_docs must be exactly [{A['stale_wiki']}], got {c['stale_docs']}")
    cat_times = {r["updated_at"] for r in revs if r["kind"] == "catalog"}
    if not (any(t < Dt for t in cat_times) and Dt in cat_times):
        fail("G2: need catalogue revisions before and at D_transfer")
    # G3 old wiki
    wiki = [r for r in revs if r["doc_key"] == A["stale_wiki"]]
    if len(wiki) != 1 or not wiki[0]["updated_at"] < Dt:
        fail("G3: the Ledger overview wiki must have one revision, before D_transfer")
    if not any(cl["p"] == "OWNS" and cl["o"] == ledger and cl["s"] == platform for cl in wiki[0]["claims"]):
        fail("G3: the Ledger overview wiki does not name Platform as owner")
    # G4 nobody else owns Ledger
    for r in revs:
        for cl in r["claims"]:
            if cl["p"] == "OWNS" and cl["o"] == ledger:
                okv = (cl["s"] == platform and cl["stated_at"] < Dt) or (cl["s"] == payments and cl["stated_at"] >= Dt)
                if not okv or cl["neg"]:
                    fail(f"G4: {r['doc_key']} states {cl['s']} owns Ledger at {iso(cl['stated_at'])}")
        for h in r["hedges"]:
            if _mentions(W, ledger, h):
                fail(f"G4: hedge about Ledger in {r['doc_key']}")
    on_chain = [x for x in world["changes"] if (x["predicate"], x["qualifier"], x["key"]) == ledger_chain]
    if [x["change_id"] for x in on_chain] != [A["ledger_transfer_change"]]:
        fail(f"G4: Ledger's OWNS chain has extra changes {[x['change_id'] for x in on_chain]}")
    if set(on_chain[0]["tags"]) & G4_EXCLUDED:
        fail("G4: Ledger's OWNS chain carries an excluded distractor")
    if gold.value(ledger_chain, today) != payments or gold.value(ledger_chain, Dt - 1) != platform:
        fail("G4: Ledger's gold owner is not Platform then Payments")

    # G5 Infra and the Payments lead
    infra_e = W.ent(infra)
    if infra_e["name"] != "Infra" or "Infrastructure" not in infra_e["aliases"]:
        fail("G5: team:infra must be named Infra with alias Infrastructure")
    if not gold.value(("LEADS", "", infra), today):
        fail("G5: Infra has no current lead")
    dup_ids = {x for pair in W.near_dup_pairs for x in pair}
    for e in W.entities():
        for n in [e["name"]] + e["aliases"]:
            toks = set(re.split(r"[^a-z0-9]+", n.lower()))
            if e["id"] != infra and "infra" in toks:
                fail(f"G5: {e['id']} uses the token Infra ({n!r})")
            if e["id"] != ledger and "ledger" in toks:
                fail(f"G5: {e['id']} uses the token Ledger ({n!r})")
    plead = gold.value(("LEADS", "", payments), today)
    if plead != A["payments_lead"]:
        fail(f"G5: Payments lead is {plead}, expected {A['payments_lead']}")
    if {infra, ledger, plead} & dup_ids:
        fail("G5: Infra, Ledger or the Payments lead is in a near_dup_name pair")
    pe = W.ent(plead)
    pnames = {n.lower() for n in [pe["name"]] + pe["aliases"]}
    first = pe["name"].split()[0].lower()
    for p in W.people:
        if p["id"] != plead and (p["name"].split()[0].lower() == first or
                                 {n.lower() for n in [p["name"]] + p["aliases"]} & pnames):
            fail(f"G5: {p['id']} makes the Payments lead ambiguous")
    if not any(r["kind"] == "roster" and any(cl["p"] == "LEADS" and cl["s"] == plead and cl["o"] == payments
                                             and cl["rank"] == 4 for cl in r["claims"]) for r in revs):
        fail("G5: the Payments lead is not stated by the roster")

    # G6 two or three Ledger authors, one outside Payments
    authors: dict[str, int] = {}
    for t in W.tickets:
        if any(a["about"] == ledger for a in t["about_timeline"]):
            authors.setdefault(t["created_by"], t["state_timeline"][0]["at"])
            for cm in t["comments"]:
                authors.setdefault(cm["author"], cm["at"])
        else:
            for cm in t["comments"]:
                if _mentions(W, ledger, " ".join(s["text"] for s in cm["sentences"])):
                    authors.setdefault(cm["author"], cm["at"])
    for r in revs:
        if r["kind"] == "chat" and _mentions(W, ledger, r["content"]):
            authors.setdefault(r["author_id"], r["updated_at"])
    if not 2 <= len(authors) <= 3:
        fail(f"G6: {len(authors)} people author tickets/messages about Ledger: {sorted(authors)}")
    if not any(gold.value(("MEMBER_OF", "primary", a), t) != payments for a, t in authors.items()):
        fail("G6: every Ledger author is in Payments")

    # G7 decision trace
    dec = {d["id"]: d for d in W.decisions}
    old, new = dec[A["adr_old"]], dec[A["adr_new"]]
    new_acc = next(s["at"] for s in new["status_timeline"] if s["status"] == "accepted")
    if ledger not in old["affects"] or not old["deciders"] or not new["deciders"]:
        fail("G7: ADRs must affect Ledger and name deciders")
    if old["status_timeline"][-1] != {"status": "superseded", "at": new_acc}:
        fail("G7: the older ADR is not superseded at the newer ADR's acceptance")
    if old["id"] not in new["replaces"]:
        fail("G7: the newer ADR does not replace the older one")
    pg, au = A["postgres"], A["aurora"]
    if not any(_mentions(W, pg, x) for x in new["rationale_points"]) or not _mentions(W, au, new["title"] + " " + new["decision_text"]):
        fail("G7: the newer ADR's reasons must name Postgres and Aurora")
    newest = max((r for r in revs if r["doc_key"] == f"adr:repo:{new['number']}"), key=lambda r: r["updated_at"])
    if not [x for x in newest["extras"] if x["section"] == "Context"]:
        fail("G7: the newer ADR has no Context reasons")
    for kind, pick in (("ticket", lambda r: r["doc_key"] == f"ticket:jira:{closed['key']}"), ("meeting", lambda r: r["kind"] == "meeting")):
        hit = False
        for r in revs:
            if not pick(r):
                continue
            for cl in r["claims"]:
                if (cl["p"], cl["s"], cl["v"], cl["form"]) == ("HAS_STATUS", new["id"], "accepted", "prose") \
                        and "because" in cl["text"] and new["number"] in cl["text"] and cl["stated_at"] >= new_acc:
                    hit = True
        if not hit:
            fail(f"G7: no {kind} sentence states {new['number']}'s acceptance with its reason")

    # G8 dependents of Ledger
    def deps_into(target: str) -> list[str]:
        return sorted(s["id"] for s in W.systems
                      if gold.value(("DEPENDS_ON", "", f"{s['id']}>{target}"), today) == "+")
    direct = deps_into(ledger)
    if not 2 <= len(direct) <= 3:
        fail(f"G8: {len(direct)} systems depend on Ledger")
    owners = {gold.value(("OWNS", "", s), today) for s in direct}
    if len(owners) < 2 or not all(gold.value(("LEADS", "", o), today) for o in owners):
        fail("G8: Ledger dependents must be owned by >= 2 teams, each with a current lead")
    if not any(x not in direct and x != ledger for d in direct for x in deps_into(d)):
        fail("G8: no two-hop dependent of Ledger")

    # G9 RDS-42
    if [s["state"] for s in rds42["state_timeline"]] != ["open"] or rds42["assignee_timeline"] \
            or [a["about"] for a in rds42["about_timeline"]] != [ledger]:
        fail("G9: RDS-42 must be open, unassigned, about Ledger")
    for r in revs:
        if any(cl["p"] == "ASSIGNED_TO" and cl["s"] == rds42["id"] for cl in r["claims"]):
            fail(f"G9: {r['doc_key']} routes RDS-42")
    if any(x["key"] == rds42["id"] for x in world["changes"]):
        fail("G9: RDS-42 has a change")
    rd = [d for d in manifest["documents"] if d["doc_key"] == f"ticket:jira:{rds42['key']}"]
    if not rd or "hyphen_id" not in rd[0]["distractors"]:
        fail("G9: RDS-42 must be tagged hyphen_id")

    # G10 reorg on D_reorg
    if Dr != Dt:
        fail("G10: D_reorg must equal D_transfer")
    org_preds = {("OWNS", ""), ("LEADS", ""), ("MEMBER_OF", "primary"), ("PART_OF", "")}
    at_reorg = [x for x in world["changes"] if x["at"] == Dr and (x["predicate"], x["qualifier"]) in org_preds]
    kinds = {(x["predicate"], x["qualifier"]) for x in at_reorg}
    if not {("OWNS", ""), ("LEADS", ""), ("MEMBER_OF", "primary")} <= kinds or len(at_reorg) < 4:
        fail(f"G10: reorg on D_reorg is too small: {sorted(kinds)}")
    for x in at_reorg:
        if x["expected_outcome"] != "resolved" or not any(
                s["states"] == "to" and s["rank"] == 4 and s["stated_at"] == Dr and s["doc_key"].split(":")[0] in ("roster", "catalog")
                for s in x["statements"]):
            fail(f"G10: {x['change_id']} is not a rank-4 roster/catalogue change on D_reorg")

    # G11 wrong challenger
    w = changes.get(A["wrong_challenger_change"])
    if not w or w["predicate"] != "OWNS" or w["key"] == ledger or "chat_contradiction" not in w["tags"] \
            or w["challenger_correct"] is not False or w["expected_outcome"] != "disputed" or w["key"] != A["wrong_challenger_system"]:
        fail("G11: anchor_wrong_challenger is missing or malformed")
    if challenger_form(w) != "chat" or "fallback_gap" in w["tags"]:
        fail("G11: anchor_wrong_challenger must be a chat challenger and not a fallback_gap")
    owner = gold.value(("OWNS", "", w["key"]), w["at"])
    lead_chain = ("LEADS", "", owner)
    if not gold.value(lead_chain, w["at"]) or not gold.value(lead_chain, today) or \
            any("fallback_gap" in x["tags"] for x in gold.all.get(lead_chain, [])):
        fail("G11: the owner team of the wrong-challenger system needs a current lead")

    # G12 demo identity
    demo = W.demo_identity
    if demo not in {p["id"] for p in W.people}:
        fail("G12: demo identity is not a person")
    if demo == plead or any(iv["p"] == "LEADS" and iv["s"] == demo for iv in W.timeline) or \
            any(cl["p"] == "LEADS" and cl["s"] == demo for r in revs for cl in r["claims"]):
        fail("G12: demo identity must not lead anything")
    if not gold.value(("MEMBER_OF", "primary", demo), today):
        fail("G12: demo identity has no team")


def check_distractors(world: dict, manifest: dict) -> dict:
    counts = defaultdict(int)
    for d in manifest["documents"]:
        for t in d["distractors"]:
            counts[t] += 1
    for c in world["changes"]:
        for t in c["tags"]:
            counts[t] += 1
    missing = [t for t in DISTRACTOR_TYPES if not counts[t]]
    if missing:
        fail(f"distractor types not represented: {missing}")
    return dict(counts)


def check_offsets(manifest: dict, files: dict[str, str]) -> None:
    import json

    chat_lines: dict[str, list[str]] = {}
    for d in manifest["documents"]:
        if d["kind"] == "chat":
            path, idx = d["path"].split("#")
            if path not in chat_lines:
                chat_lines[path] = files[path].rstrip("\n").split("\n")
            text = json.loads(chat_lines[path][int(idx)])["text"]
        else:
            text = files[d["path"]]
        for s in d["sentences"]:
            if text[s["char_start"]:s["char_end"]] != s["text"]:
                fail(f"offsets: {d['path']} [{s['char_start']}:{s['char_end']}] does not slice to its sentence")


def run_all(W, world: dict, manifest: dict, revs: list[dict], files: dict[str, str]) -> dict:
    changes = world["changes"]
    check_names(W)
    check_offsets(manifest, files)
    check_rank_rule(changes)
    check_stale_docs(changes, manifest)
    gold = DeclaredGold(changes, revs)
    check_consistency(changes, gold)
    check_coverage(W, gold)
    cells = check_balance(changes)
    check_anchor(W, world, manifest, revs, gold)
    counts = check_distractors(world, manifest)
    return {"balance": cells, "distractors": counts}
