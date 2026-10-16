"""Answer layer (06 §4) on a fixed sample (~10 questions per category, chosen once by seed, A63).

Variants: `A` = the agent restricted to span search (text-only answers), `D` = the full agent.
Metrics: entity match (hit rate) and entity F1, citation precision/recall, verifier pass rates before
re-draft, draft citations (must be 0), dispute disclosure, proposal labelling, action citation (past
belief), abstention precision/recall, stale-fact error, aggregate outcome (category 10), the
history-phrasing LLM judge (categories 5/7/8 only; fixed rubric; cached; skipped when the LLM is off),
and latency per stage.

Scripted questions (`setup_script`, `turns`, `session: token`) run on an ISOLATED scratch graph per
script (A63: `reset_seed` into a fresh graph name, torn down afterwards); questions sharing a script
share one graph. The script's results resolve `gold_action_ids`, `gold_proposal_ids`, `belief_at` and the
`{date}` placeholder in the question. Two-turn scripts run both turns in one token session; only the
last turn is scored, with turn-1's stored span as gold evidence.

Stage latency is derived from the event stream: the runner timestamps each event as the generator
yields it (no change to `api/agent.py`), so plan = until the `plan` event, tools = until the last
`tool_result`, draft = until `draft`, verify = until `verification` (includes one re-draft, if any).

`python -m evals.answer [--seeds 1 2] [--cats 7 9 10 4-pending] [--variants D] [--per-cat 10]`
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import random
import re
import statistics
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from api.agent import Agent, Session
from brain import providers
from brain.actions import Actions, Actor, Refused
from brain.config import ROOT
from brain.db import Graph

from .gold import World
from .questions import label_of

NUMBER_WORDS = {0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight",
                9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}
JUDGE_CATS = {5, 7, 8}
JUDGE_RUBRIC = (
    "You grade how an assistant phrased TIME in an answer about company facts. Score 1 only if ALL hold: "
    "(a) every fact marked historical/superseded is phrased in the past tense or explicitly labelled as "
    "historical/former; (b) no fact that the answer itself marks historical, superseded or proposed is "
    "stated as if it were current; (c) disputed facts are called disputed and both sides are named; "
    "(d) for a question about a past action ('why did you route ... on <date>'), the answer refers to what "
    "was believed at that time (then), not only to what is true now. An abstention ('no verified answer') "
    "scores 0. Return JSON {\"score\": 0 or 1, \"reason\": short string}.")


class TextOnlyAgent(Agent):
    def tool_calls(self, plan, text, ctx, s):
        return [("search_spans", {"query": text})]


VARIANT_AGENTS = {"A": TextOnlyAgent, "D": Agent}


def sample(qs: list[dict], per_cat: int, seed: int) -> list[dict]:
    rnd = random.Random(1000 + seed)
    by = defaultdict(list)
    for q in qs:
        by[label_of(q)].append(q)
    out = []
    for cat in sorted(by, key=_label_key):
        out += sorted(rnd.sample(by[cat], min(per_cat, len(by[cat]))), key=lambda q: q["id"])
    return out


def _label_key(lab: str) -> tuple:
    num, _, tag = lab.partition("-")
    return (int(num), tag)


def _iso(ms: int | None) -> str:
    return dt.datetime.fromtimestamp((ms or 0) / 1000, dt.timezone.utc).strftime("%Y-%m-%d")


def _cited_entities(ans: dict) -> set[str]:
    out = set()
    for c in ans["claims"]:
        f = c.get("fact") or {}
        for k in ("subject_id", "object_id"):
            if f.get(k):
                out.add(f[k])
    return out


# Setup scripts (A63: isolated scratch graph per script)

def script_key(q: dict) -> str | None:
    """Questions needing scratch state: those with a setup script, several turns or a token session.
    Questions with the same key share one scratch graph (one reset)."""
    if not (q.get("setup_script") or q.get("turns") or q.get("session") == "token"):
        return None
    return hashlib.sha1(json.dumps(q.get("setup_script") or [], sort_keys=True).encode()).hexdigest()[:10]


def run_setup(g: Graph, steps: list[dict], world: World) -> dict[str, dict]:
    """Execute the declarative steps; return {ref: {action_id, recorded_at, produced, ...}}."""
    acts = Actions(g)
    refs: dict[str, dict] = {}
    demo = world.w.get("demo_identity") or world.w["people"][0]["id"]
    for st in steps:
        op, ref = st["op"], st.get("ref") or f"step{len(refs)}"
        if op == "set_as_of":
            refs[ref] = {"as_of": st["value"]}
            continue
        actor = Actor(st.get("as") or demo, client="eval")
        try:
            if op == "route_to_owner":
                res = acts.route_to_owner(actor, ticket_id=st["ticket"])
            elif op == "draft_adr_supersession":
                res = acts.draft_adr_supersession(actor, st["decision"], st.get("reason", "eval draft"))
            elif op == "confirm":
                tgt = refs.get(st["target"], {})
                res = acts.confirm_fact(actor, action_id=tgt.get("action_id")) if tgt.get("action_id") else \
                    acts.confirm_fact(actor, assertion_id=st["target"])
            elif op == "learn_fact":
                res = _learn_via_agent(g, actor.person_id, st["text"])
            else:
                refs[ref] = {"refused": f"unknown op {op}"}
                continue
        except Refused as r:
            refs[ref] = {"refused": r.reason}
            continue
        except Exception as e:  # noqa: BLE001
            refs[ref] = {"refused": f"{type(e).__name__}: {e}"}
            continue
        aid = res.get("action_id")
        a = acts._action(aid) if aid else None
        produced = acts._produced(aid)[0] if aid else []
        refs[ref] = {**res, "action_id": aid, "recorded_at": (a or {}).get("recorded_at"), "produced": produced}
    return refs


def _learn_via_agent(g: Graph, person: str, text: str) -> dict:
    """A learn_fact step goes through the agent (the statement must be a user turn of a session, A9)."""
    ag = Agent(g)
    s = ag.create_session(f"eval_setup_{person}", person)
    for ev in ag.turn(s, text):
        if ev["event"] == "action" and ev.get("status") == "done":
            return ev["result"]
        if ev["event"] == "refusal":
            raise Refused(ev.get("reason", "refused"))
    raise Refused("no learn_fact action was taken")


def resolve(q: dict, refs: dict[str, dict]) -> dict:
    """Fill gold_action_ids / gold_proposal_ids / belief_at / {date} from the executed script."""
    q = dict(q)
    hits = [refs.get(r) for r in q.get("gold_action_refs") or []]
    if any(h is None or h.get("refused") for h in hits):
        q["setup_failed"] = [h.get("refused") if h else "missing ref" for h in hits]
        return q
    if hits:
        q["gold_action_ids"] = [h["action_id"] for h in hits]
        q["gold_proposal_ids"] = [p for h in hits for p in h.get("produced", [])]
        t = max(h["recorded_at"] for h in hits)
        if q.get("belief_at_from_action"):
            q["belief_at"] = t
        q["question"] = q["question"].replace("{date}", _iso(t))
        q["turns"] = [x.replace("{date}", _iso(t)) for x in (q.get("turns") or [])] or None
    for r in refs.values():
        if "as_of" in r:
            q["as_of"] = r["as_of"]
    return q


# One question

def _timed_turn(agent: Agent, s: Session, text: str, as_of: int | None, belief_at: int | None) -> tuple[list, dict]:
    """Run a turn, timestamping each event as the generator yields it; derive per-stage latency."""
    t0 = time.perf_counter()
    events, stamps = [], []
    for ev in agent.turn(s, text, as_of=as_of, belief_at=belief_at):
        events.append(ev)
        stamps.append((time.perf_counter() - t0) * 1000)
    at = {}
    for ev, ms in zip(events, stamps):
        at.setdefault(ev["event"], ms)
        if ev["event"] == "tool_result":
            at["last_tool"] = ms
    plan = at.get("plan", 0.0)
    tools_end = at.get("last_tool", plan)
    draft = at.get("draft", tools_end)
    verify = at.get("verification", draft)
    stages = {"plan_ms": round(plan, 1), "tools_ms": round(tools_end - plan, 1), "draft_ms": round(draft - tools_end, 1),
              "verify_ms": round(verify - draft, 1), "latency_ms": round(stamps[-1] if stamps else 0.0, 1)}
    return events, stages


def _session_user_spans(g: Graph, sid: str) -> list[str]:
    rows = g.ro("MATCH (:Source {id:$s})-[:HAS_SPAN]->(x:Span) WHERE x.author_role = 'user' "
                "RETURN x.id AS id ORDER BY x.ordinal", {"s": sid}, template="eval_session_spans")
    return [r["id"] for r in rows]


JUDGE_QUESTIONS = {
    "rubric": {"type": "noul", "instructions": JUDGE_RUBRIC.rsplit(" Return JSON", 1)[0],
               "criteria": {"true": "All of (a)-(d) hold.", "false": "Any of (a)-(d) fails, or the answer abstains."}},
    "reference": {"type": "score", "instructions": "How closely does the ANSWER agree with the REFERENCE on the facts "
                                                   "and on when each held?",
                  "criteria": ["Contradicts the reference or misses its facts", "Partly agrees",
                               "The same facts with the same timing"]}}
LOW_CONFIDENCE = (0.3, 0.7)


def _sampled(q: dict) -> bool:
    """The fixed 20% of judged questions that both judges score (an agreement rate, item 20 step 0)."""
    return int(hashlib.sha256(f"{q.get('_seed')}:{q['id']}".encode()).hexdigest(), 16) % 5 == 0


def _second_judge(body: str) -> dict | None:
    try:
        res = providers.complete([{"role": "system", "content": JUDGE_RUBRIC.replace('{\"score\": 0 or 1', '{\"verdict\": 0 or 1')
                                   + " Give the verdict first."}, {"role": "user", "content": body}],
                                 schema={"type": "object", "properties": {"verdict": {"type": "integer"},
                                                                          "reason": {"type": "string"}},
                                         "required": ["verdict"]}, role="judge2")
    except Exception:  # noqa: BLE001
        return None
    j = res.get("json") or {}
    try:
        return {"score": 1.0 if int(j.get("verdict", 0)) >= 1 else 0.0, "reason": str(j.get("reason", ""))[:200],
                "model": res.get("model")}
    except (TypeError, ValueError):
        return None


def judge_agreement(rows: list[dict]) -> tuple[float | None, int]:
    both = [r for r in rows if r.get("judge1_score") is not None and r.get("judge2_score") is not None]
    return (sum(r["judge1_score"] == r["judge2_score"] for r in both) / len(both) if both else None), len(both)


def cost_per_answer(n: int) -> float:
    """usage.cost of the answering roles (not the judges), per question, this process."""
    return sum(c for (role, _), c in providers.COSTS.items() if role not in ("judge", "judge2")) / n if n else 0.0


def judge_history(q: dict, ans: dict) -> dict | None:
    """History-phrasing judge (06 §4), item 20 step 0: the decision judge scores the fixed rubric and agreement
    with the question's reference answer; a low-confidence rubric verdict is decided by the second (chat)
    judge, and a fixed 20% sample goes to both. Cached by prompt. None when the LLM is off."""
    if q["category"] not in JUDGE_CATS or not providers.llm_available():
        return None
    lines = [f"- [{l['status']}] {l['text']}" for l in ans["assembled"]["lines"]]
    body = (f"QUESTION: {q['question']}\nAS_OF: {_iso(q.get('as_of'))}"
            + (f"\nBELIEF_AT: {_iso(q['belief_at'])}" if q.get("belief_at") else "")
            + ("\nANSWER: (abstained)" if ans["abstained"] else
               (f"\nANSWER: {ans['assembled']['lead']}" if ans["assembled"].get("lead") else "")
               + "\nANSWER LINES:\n" + "\n".join(lines))
            + (f"\nEXPLANATION: {ans['assembled'].get('explanation', '')[:800]}" if ans["assembled"].get("explanation") else "")
            + (f"\nREFERENCE: {q['reference_answer']}" if q.get("reference_answer") else ""))
    out = {"judge": None, "p": None, "reference_match": None, "judge1_score": None, "judge2": None,
           "judge2_score": None, "low_confidence": False, "sampled": _sampled(q)}
    try:
        res = providers.decide("judge", body, JUDGE_QUESTIONS)
        out["p"] = providers.decision_p(res, "rubric")
        out["reference_match"] = providers.decision_p(res, "reference")
        out["judge"] = res["model"]
        if out["p"] is not None:
            out["judge1_score"] = 1.0 if out["p"] >= 0.5 else 0.0
    except Exception:  # noqa: BLE001 - both decision judges down: the second judge alone
        pass
    out["low_confidence"] = out["p"] is None or LOW_CONFIDENCE[0] < out["p"] < LOW_CONFIDENCE[1]
    second = _second_judge(body) if out["low_confidence"] or out["sampled"] else None
    if second:
        out["judge2"], out["judge2_score"] = second["model"], second["score"]
    score = second["score"] if out["low_confidence"] and second else out["judge1_score"]
    if score is None:
        return None
    return {**out, "score": score, "reason": second["reason"] if out["low_confidence"] and second else ""}


def evaluate(agent: Agent, q: dict, as_of: int, variant: str = "D") -> dict:
    names = World_names.get(q["_seed"], {})
    if q.get("setup_failed"):
        return {"id": q["id"], "category": q["category"], "label": label_of(q), "anchor": q["anchor"],
                "setup_failed": q["setup_failed"], "abstained": None, "must_abstain": q["must_abstain"]}
    token = q.get("session") == "token"
    if token:
        s = agent.create_session(f"eval_{variant}_{q['id']}", q.get("acting_as") or "")
    else:
        s = Session("eval_" + q["id"], "eval", "", anonymous=True)
    turns = list(q.get("turns") or [q["question"]])
    gold_groups = [list(g) for g in q["gold_evidence_groups"]]
    gold_actions = list(q.get("gold_action_ids") or [])
    prior_actions: list[str] = []
    for i, text in enumerate(turns[:-1]):
        evs, _ = _timed_turn(agent, s, text, as_of, None)
        prior_actions += [e["action_id"] for e in evs if e["event"] == "action" and e.get("action_id")]
        if q.get("gold_action_from_turn") == i:
            gold_actions += [e["action_id"] for e in evs if e["event"] == "action" and e.get("action_id")]
    if token and q.get("gold_turn_spans"):
        spans = _session_user_spans(agent.g, s.id)
        gold_groups += [[spans[i]] for i in q["gold_turn_spans"] if i < len(spans)]
    events, stages = _timed_turn(agent, s, turns[-1], q.get("as_of") or as_of, q.get("belief_at"))
    ans = next(e for e in events if e["event"] == "answer")
    ver = next(e for e in events if e["event"] == "verification")
    packs = ans["packs"]
    span_meta = {sp["span_id"]: sp for p in packs.values() for it in p["items"] for sp in it["spans"]}
    cited = {sid for c in ans["claims"] for sid in c.get("span_ids", [])}
    gold = {s_ for g in gold_groups for s_ in g}
    ents = _cited_entities(ans)
    texts = " ".join(sp["text"] for sid, sp in span_meta.items() if sid in cited).lower()
    answer_text = ((ans["assembled"].get("lead") or "") + " ").lstrip() + " ".join(l["text"] for l in ans["assembled"]["lines"]) + " " + (ans["assembled"].get("explanation") or "")
    exp = q.get("expected_entities") or []
    entity = entity_p = entity_f1 = None
    if exp:
        hit = [e for e in exp if e in ents or (names.get(e, "~~").lower() in texts)]
        entity = len(hit) / len(exp)
        asked = {e for e, nm in names.items() if nm and nm.lower() in q["question"].lower()}   # anchors the question names
        cited_ents = ents - asked
        if cited_ents:
            entity_p = len(cited_ents & set(exp)) / len(cited_ents)
            entity_f1 = (2 * entity_p * entity / (entity_p + entity)) if entity_p + entity else 0.0
    draft_cites = sum(1 for sid in cited if span_meta.get(sid, {}).get("kind") == "draft")
    disclosure = None
    if q.get("expected_dispute"):
        d = q["expected_dispute"]
        disputed_claims = [c for c in ans["claims"] if c.get("disputed")]
        both_named = all(x in ents or names.get(x, "~~").lower() in texts for x in (d["recorded"], d["challenger"]))
        disclosure = 1.0 if (disputed_claims and both_named) else 0.0
    stale_err = None
    if q["forbidden_current_spans"]:
        fb = set(q["forbidden_current_spans"])
        stale_err = 1.0 if any(c.get("tense") == "current" and fb & set(c.get("span_ids", [])) for c in ans["claims"]) else 0.0
    # proposal labelling (06 §4): tense proposed + cites the producing action; a proposal stated as current
    # is also a stale-fact error
    proposal = proposal_as_current = None
    gold_props = set(q.get("gold_proposal_ids") or [])
    if q.get("expected_tense") == "proposed" and gold_actions:
        ok = any(c.get("tense") == "proposed" and set(c.get("action_ids", [])) & set(gold_actions)
                 and (not gold_props or set(c.get("assertion_ids", [])) & gold_props) for c in ans["claims"])
        proposal = 1.0 if ok else 0.0
        proposal_as_current = 1.0 if any(c.get("tense") == "current" and set(c.get("assertion_ids", [])) & gold_props
                                         for c in ans["claims"]) else 0.0
        if proposal_as_current:
            stale_err = 1.0
    # action citation: any kept claim cites a gold action (past belief, learn_fact recall)
    action_cited = None
    if gold_actions:
        pack_actions = {a.get("action_id") for p in packs.values() for it in p["items"] for a in (it.get("actions") or [])}
        action_cited = 1.0 if any(set(c.get("action_ids", [])) & set(gold_actions) for c in ans["claims"]) else 0.0
        action_in_pack = 1.0 if pack_actions & set(gold_actions) else 0.0
    else:
        action_in_pack = None
    # category 10: a correct answer (any label) or an abstention are both acceptable
    agg = None
    if q.get("expected_answer"):
        ea = q["expected_answer"]
        low = answer_text.lower()
        if "number" in ea:
            n = ea["number"]
            correct = bool(re.search(rf"(?<![\d.]){n}(?![\d.])", low)) or \
                (n in NUMBER_WORDS and re.search(rf"\b{NUMBER_WORDS[n]}\b", low) is not None)
        else:
            correct = ea["entity"] in ents or names.get(ea["entity"], "~~").lower() in low
        agg = "abstain" if ans["abstained"] else ("correct" if correct else "wrong")
    judge = judge_history(q, ans)
    dropped_rules = [d["rule"] for d in ver["dropped"]]
    n_claims = len(ans["claims"]) + len(ver["dropped"])
    labels = sorted({c.get("label") for c in ans["claims"]})
    return {"id": q["id"], "category": q["category"], "label": label_of(q), "anchor": q["anchor"],
            "tmpl": q.get("tmpl"), "abstained": ans["abstained"], "must_abstain": q["must_abstain"],
            "entity_match": entity, "entity_precision": entity_p, "entity_f1": entity_f1,
            "citation_precision": (len(cited & gold) / len(cited)) if cited and gold else None,
            "citation_recall": (sum(1 for g in gold_groups if set(g) & cited) / len(gold_groups)) if gold_groups else None,
            "v2_pass": None if not n_claims else 1 - dropped_rules.count("V2") / n_claims,
            "v3_pass": None if not n_claims else 1 - dropped_rules.count("V3") / n_claims,
            "draft_citations": draft_cites, "dispute_disclosure": disclosure, "stale_error": stale_err,
            "proposal_labelling": proposal, "proposal_as_current": proposal_as_current,
            "action_cited": action_cited, "action_in_pack": action_in_pack,
            "aggregate_outcome": agg, "aggregate_acceptable": None if agg is None else (1.0 if agg != "wrong" else 0.0),
            "aggregate_correct": None if agg is None else (1.0 if agg == "correct" else 0.0),
            "history_judge": None if judge is None else judge["score"],
            "history_judge_reason": None if judge is None else judge["reason"],
            **({k: judge[k] for k in ("judge", "p", "reference_match", "judge1_score", "judge2", "judge2_score",
                                      "low_confidence", "sampled")} if judge else {}),
            "claim_labels": labels, "gold_action_ids": gold_actions, "answer": answer_text[:400], **stages}


World_names: dict[int, dict[str, str]] = {}


# The run

def _pool_map(fn, xs: list) -> list:
    # turns are I/O-bound on the LLM: run them concurrently
    with ThreadPoolExecutor(max_workers=int(os.environ.get("BRAIN_EVAL_WORKERS", "6"))) as pool:
        return list(pool.map(fn, xs))


def run(seeds: list[int], out: Path, per_cat: int = 10, cats: list[str] | None = None,
        variants: list[str] | None = None) -> str:
    variants = variants or ["A", "D"]
    rows_by_v: dict[str, list[dict]] = defaultdict(list)
    setup_log: list[dict] = []
    for seed in seeds:
        seed_dir = ROOT / "world" / "seeds" / str(seed)
        world = World.load(seed_dir)
        World_names[seed] = world.names()
        g = Graph(name=f"eval_seed{seed}")
        qs = [json.loads(l) for l in (out / f"questions-seed{seed}.jsonl").read_text().splitlines()]
        for q in qs:
            q["_seed"] = seed
        smp = sample(qs, per_cat, seed)
        if cats:
            smp = [q for q in smp if label_of(q) in cats]
        plain = [q for q in smp if script_key(q) is None]
        groups: dict[str, list[dict]] = defaultdict(list)
        for q in smp:
            k = script_key(q)
            if k:
                groups[k].append(q)
        for v in variants:
            if plain:
                agent = VARIANT_AGENTS[v](g)
                rows_by_v[v] += _pool_map(lambda q: {"seed": seed, "variant": v, **evaluate(agent, q, world.today, v)}, plain)
        # scripted questions: one scratch graph per script, torn down afterwards (A63)
        for key, qsg in groups.items():
            from brain.cli import reset_seed
            sg = Graph(name=f"eval_scratch_{seed}_{key}")
            t0 = time.time()
            try:
                reset_seed(sg, str(seed_dir))
                steps = qsg[0].get("setup_script") or []
                refs = run_setup(sg, steps, world)
                setup_log.append({"seed": seed, "graph": sg.name, "steps": len(steps), "questions": len(qsg),
                                  "refused": {r: x["refused"] for r, x in refs.items() if x.get("refused")},
                                  "seconds": round(time.time() - t0, 1)})
                resolved = [resolve(q, refs) for q in qsg]
                for v in variants:
                    agent = VARIANT_AGENTS[v](sg)
                    rows_by_v[v] += _pool_map(lambda q: {"seed": seed, "variant": v, **evaluate(agent, q, world.today, v)},
                                              resolved)
            finally:
                try:
                    sg.delete()
                except Exception:  # noqa: BLE001
                    pass
    for v in variants:
        (out / f"answer-{v}.jsonl").write_text("\n".join(json.dumps(r) for r in rows_by_v[v]))
    (out / "answer-setup.json").write_text(json.dumps(setup_log, indent=1))
    n = sum(len(r) for r in rows_by_v.values())
    agree, both = judge_agreement([r for v in variants for r in rows_by_v[v]])
    (out / "judges.json").write_text(json.dumps({
        "judge": providers.role_models("judge"), "judge2": providers.role_models("judge2"),
        "answer_models": {r: providers.role_models(r) for r in ("planner", "drafter", "checker", "escalation")},
        "agreement": agree, "agreement_n": both, "cost_per_answer_usd": round(cost_per_answer(n), 6),
        "cost_usd": {f"{r}:{m}": round(c, 6) for (r, m), c in providers.COSTS.items()}}, indent=1))
    text = summary(rows_by_v, variants, seeds, per_cat, setup_log)
    (out / "answer-summary.md").write_text(text)
    return text


METRICS = ["entity_match", "entity_f1", "citation_precision", "citation_recall", "v2_pass", "v3_pass",
           "dispute_disclosure", "stale_error", "proposal_labelling", "proposal_as_current", "action_cited",
           "action_in_pack", "aggregate_acceptable", "aggregate_correct", "history_judge"]
CAT_LABELS = {"1": "single-hop", "2": "multi-hop", "3": "ownership", "4": "decision trace", "4-pending": "pending draft",
              "5": "stale fact", "6": "unanswerable", "7": "past belief", "8": "disputed", "9": "session memory",
              "10": "outside templates", "11": "graph algorithms"}


def _mean_cell(rows: list[dict], m: str) -> str:
    xs = [r.get(m) for r in rows if r.get(m) is not None]
    return f"{statistics.mean(xs):.3f} (n={len(xs)})" if xs else "—"


def _pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, int(len(xs) * p) - 1))] if xs else 0.0


def summary(rows_by_v: dict[str, list[dict]], variants: list[str], seeds: list[int], per_cat: int,
            setup_log: list[dict]) -> str:
    lines = ["# Answer layer", "", f"Fixed sample of up to {per_cat} questions per category per seed; seeds {seeds}.", ""]
    hdr = "| Metric | " + " | ".join(f"{v} ({'text-only' if v == 'A' else 'graph'} agent)" for v in variants) + " |"
    lines += [hdr, "|---|" + "---|" * len(variants)]
    for m in METRICS:
        cells = [_mean_cell([r for r in rows_by_v[v] if "setup_failed" not in r], m) for v in variants]
        if any(c != "—" for c in cells):
            lines.append(f"| {m} | " + " | ".join(cells) + " |")
    for v in variants:
        rs = [r for r in rows_by_v[v] if "setup_failed" not in r]
        tp = sum(1 for r in rs if r["abstained"] and r["must_abstain"])
        fp = sum(1 for r in rs if r["abstained"] and not r["must_abstain"])
        fn = sum(1 for r in rs if not r["abstained"] and r["must_abstain"])
        lines.append(f"| abstention P/R ({v}) | {tp / (tp + fp) if tp + fp else 0:.2f} / {tp / (tp + fn) if tp + fn else 0:.2f} |"
                     + " |" * (len(variants) - 1))
        for st in ("plan_ms", "tools_ms", "draft_ms", "verify_ms", "latency_ms"):
            xs = [r[st] for r in rs if r.get(st) is not None]
            lines.append(f"| {st} p50/p95 ({v}) | {_pct(xs, .5):.0f} / {_pct(xs, .95):.0f} |" + " |" * (len(variants) - 1))
        lines.append(f"| draft citations, final ({v}) | {sum(r['draft_citations'] for r in rs)} (must be 0) |"
                     + " |" * (len(variants) - 1))
        agree, both = judge_agreement(rs)
        if both:
            lines.append(f"| judge agreement ({v}) | {agree:.2f} (n={both}) |" + " |" * (len(variants) - 1))
        failed = [r["id"] for r in rows_by_v[v] if "setup_failed" in r]
        if failed:
            lines.append(f"| setup failed, skipped ({v}) | {len(failed)}: {', '.join(failed[:8])} |" + " |" * (len(variants) - 1))
    # per category
    for v in variants:
        rs = [r for r in rows_by_v[v] if "setup_failed" not in r]
        labs = sorted({r["label"] for r in rs}, key=_label_key)
        per_cat_metrics = ["entity_match", "entity_f1", "citation_recall", "dispute_disclosure", "stale_error",
                           "proposal_labelling", "action_cited", "action_in_pack", "aggregate_acceptable",
                           "aggregate_correct", "history_judge"]
        lines += ["", f"## Per category, variant {v}", "", "| Category | n | abstained | " + " | ".join(per_cat_metrics) + " |",
                  "|---|---|---|" + "---|" * len(per_cat_metrics)]
        for lab in labs:
            xs = [r for r in rs if r["label"] == lab]
            cells = [_mean_cell(xs, m) for m in per_cat_metrics]
            lines.append(f"| {lab} {CAT_LABELS.get(lab, '')} | {len(xs)} | {sum(1 for r in xs if r['abstained'])} | "
                         + " | ".join(cells) + " |")
        agg = [r for r in rs if r.get("aggregate_outcome")]
        if agg:
            c = defaultdict(int)
            for r in agg:
                c[r["aggregate_outcome"]] += 1
            unl = sum(1 for r in agg if "unverified_path" in (r.get("claim_labels") or []))
            lines.append(f"\nCategory 10 outcomes ({v}): " + ", ".join(f"{k}={n}" for k, n in sorted(c.items()))
                         + f"; answers using an unverified_path claim: {unl}")
        pb = [r for r in rs if r["label"] == "7"]
        if pb:
            by_t = defaultdict(list)
            for r in pb:
                by_t[r.get("tmpl")].append(r)
            lines.append(f"\nCategory 7 by phrasing template ({v}): " + "; ".join(
                f"t{t}: action_cited={_mean_cell(xs, 'action_cited')}, entity={_mean_cell(xs, 'entity_match')}"
                for t, xs in sorted(by_t.items(), key=lambda kv: str(kv[0]))))
    if setup_log:
        lines += ["", "## Setup scripts (scratch graphs, torn down)", ""]
        for s in setup_log:
            lines.append(f"- seed {s['seed']} `{s['graph']}`: {s['steps']} steps, {s['questions']} questions, "
                         f"{s['seconds']} s" + (f", refused: {s['refused']}" if s["refused"] else ""))
    return "\n".join(lines) + "\n"


def main() -> None:
    from .run import sha
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", nargs="+", type=int, default=[1, 2, 3])
    ap.add_argument("--cats", nargs="*", default=None, help="category labels, e.g. 7 9 10 4-pending")
    ap.add_argument("--variants", nargs="*", default=None, choices=list(VARIANT_AGENTS))
    ap.add_argument("--per-cat", type=int, default=10)
    ap.add_argument("--out", default=None, help="results dir (default evals/results/<git-sha>)")
    ap.add_argument("seeds_pos", nargs="*", type=int, help="(legacy) seeds as positional args")
    a = ap.parse_args()
    seeds = a.seeds_pos or a.seeds
    out = Path(a.out) if a.out else ROOT / "evals" / "results" / sha()
    out.mkdir(parents=True, exist_ok=True)
    print(run(seeds, out, a.per_cat, a.cats, a.variants))


if __name__ == "__main__":
    main()
