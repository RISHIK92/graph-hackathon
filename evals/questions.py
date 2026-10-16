"""Question generators per category (06 §6). Gold is copied from the declarations (05 §3.3), never
computed by a chain function. Phrasings come from 3–5 templates per category."""
from __future__ import annotations

import random
from collections import defaultdict

from brain.db import Graph

from .gold import ChainGold, SpanGold, World, chain_key

DAY = 86_400_000


def _pick(rnd: random.Random, xs: list, k: int) -> list:
    xs = list(xs)
    rnd.shuffle(xs)
    return xs[:k]


class Generator:
    def __init__(self, world: World, g: Graph, seed: int = 0):
        self.world, self.g = world, g
        self.cg = ChainGold(world)
        self.sg = SpanGold(world, g)
        self.names = world.names()
        self.rnd = random.Random(seed)
        self.today = world.today
        self.anchor_ids: set[str] = set()
        for v in (world.w.get("anchor") or {}).values():
            self.anchor_ids |= set(v) if isinstance(v, list) else {v}
        self.fact_by_chain_value: dict[tuple, list[str]] = defaultdict(list)
        for f in world.w["facts"]:
            key = chain_key(f["predicate"], f.get("qualifier") or "", f["subject"], f.get("object") or "")
            self.fact_by_chain_value[(key, self.cg._value(f["predicate"], f))].append(f["fact_id"])

    # gold evidence
    def group(self, key: tuple, value: str) -> list[str]:
        """Spans that state `value` for chain `key`: its facts plus change statements of that value."""
        spans: list[str] = []
        for fid in self.fact_by_chain_value.get((key, value), []):
            spans += self.sg.spans(f"fact:{fid}")
        for c in self.cg.changes.get(key, []):
            if c["to"] == value:
                spans += self.sg.spans(f"change:{c['change_id']}", states="to")
            if c["from"] == value:
                spans += self.sg.spans(f"change:{c['change_id']}", states="from")
        return sorted(set(spans))

    def stale_spans(self, key: tuple, old: str, new_since: int) -> list[str]:
        """Spans stating a replaced value in a document's latest revision (forbidden as current)."""
        out = []
        for c in self.cg.changes.get(key, []):
            if c["expected_outcome"] != "resolved" or c["from"] != old:
                continue
            for d in c.get("stale_docs") or []:
                for s in self.sg.by_ref.get(f"change:{c['change_id']}", []):
                    if s["doc"]["doc_key"] == d and s.get("states") == "from":
                        out += self.sg.spans(f"change:{c['change_id']}", states="from")
        return sorted(set(out))

    def q(self, cat: int, text: str, **kw) -> dict:
        ents = kw.get("expected_entities", [])
        return {"id": f"c{cat}-{len(self.out[cat]) + 1:03d}", "category": cat, "question": text,
                "as_of": kw.pop("as_of", self.today), "belief_at": None, "expected_entities": ents,
                "expected_fact": kw.pop("expected_fact", None), "gold_evidence_groups": kw.pop("groups", []),
                "forbidden_current_spans": kw.pop("forbidden", []), "expected_relation_types": kw.pop("rel", []),
                "must_abstain": kw.pop("must_abstain", False), "expected_dispute": kw.pop("dispute", None),
                "challenger_correct": kw.pop("challenger_correct", None), "change_id": kw.pop("change_id", None),
                "anchor": any(e in self.anchor_ids for e in ents) or kw.pop("anchor", False), **kw}

    # categories
    def build(self, per_cat: int = 50) -> list[dict]:
        self.out: dict[int, list[dict]] = defaultdict(list)
        T = self.today
        n = self.names
        systems = [s["id"] for s in self.world.w["systems"]]
        # 3 ownership + 8 disputed share "Who owns X?" phrasing
        own_t = ["Who owns {x}?", "Which team is responsible for {x}?", "Who is the owner of {x} today?",
                 "Who should I talk to about {x} ownership?"]
        for x in systems + [p["id"] for p in self.world.w["projects"]]:
            key = ("OWNS", "", x)
            st = self.cg.state(key, T)
            if not st:
                continue
            for tmpl in own_t[:3]:
                if st["disputes"]:
                    d = st["disputes"][0]
                    self.out[8].append(self.q(8, tmpl.format(x=n[x]), expected_entities=[st["value"], d["challenger"]],
                                              expected_fact={"subject_id": st["value"], "predicate": "OWNS", "object_id": x},
                                              groups=[self.group(key, st["value"]), self.group(key, d["challenger"])],
                                              dispute={"recorded": st["value"], "challenger": d["challenger"]},
                                              challenger_correct=d["challenger_correct"], change_id=d["change_id"],
                                              rel=["OWNS"]))
                else:
                    # The answer names the owner team's lead too (M4, item 20), so its declaration is gold.
                    lead = self.cg.state(("LEADS", "", st["value"]), T) if st["value"].startswith("team:") else None
                    groups = [self.group(key, st["value"])] + \
                        ([self.group(("LEADS", "", st["value"]), lead["value"])] if lead else [])
                    self.out[3].append(self.q(3, tmpl.format(x=n[x]), expected_entities=[st["value"]],
                                              expected_fact={"subject_id": st["value"], "predicate": "OWNS", "object_id": x},
                                              groups=groups, rel=["OWNS"]))
        for t in self.world.w["tickets"]:
            key = ("ASSIGNED_TO", "", t["id"])
            st = self.cg.state(key, T)
            if st and len(self.out[3]) < per_cat * 2:
                self.out[3].append(self.q(3, f"Who should I ask about {t['key']}?", expected_entities=[st["value"]],
                                          expected_fact={"subject_id": t["id"], "predicate": "ASSIGNED_TO",
                                                         "object_id": st["value"]},
                                          groups=[self.group(key, st["value"])], rel=["ASSIGNED_TO"]))
        # 1 single-hop: PART_OF and ADR decisions
        for x in systems:
            key = ("PART_OF", "", x)
            st = self.cg.state(key, T)
            if st:
                for tmpl in ("Which project is {x} part of?", "What project does {x} belong to?"):
                    self.out[1].append(self.q(1, tmpl.format(x=n[x]), expected_entities=[st["value"]],
                                              expected_fact={"subject_id": x, "predicate": "PART_OF",
                                                             "object_id": st["value"]},
                                              groups=[self.group(key, st["value"])], rel=["PART_OF"]))
        for d in self.world.w["decisions"]:
            key = ("HAS_STATUS", "", d["id"])
            st = self.cg.state(key, T)
            if st:
                for tmpl in ("What does {a} decide?", "What is the status of {a}?"):
                    self.out[1].append(self.q(1, tmpl.format(a=d["number"]), expected_entities=[d["id"]],
                                              expected_fact={"subject_id": d["id"], "predicate": "HAS_STATUS",
                                                             "object_value": st["value"].lstrip("=")},
                                              groups=[self.group(key, st["value"])], rel=["HAS_STATUS"]))
        # 2 multi-hop: lead of the owner, and impact
        for x in systems:
            own = self.cg.state(("OWNS", "", x), T)
            if not own or not own["value"].startswith("team:"):
                continue
            lead = self.cg.state(("LEADS", "", own["value"]), T)
            if lead and lead["value"]:
                for tmpl in ("Who leads the team that owns {x}?", "Who manages the owners of {x}?"):
                    self.out[2].append(self.q(2, tmpl.format(x=n[x]), expected_entities=[lead["value"]],
                                              groups=[self.group(("OWNS", "", x), own["value"]),
                                                      self.group(("LEADS", "", own["value"]), lead["value"])],
                                              rel=["OWNS", "LEADS"]))
            deps = self._dependents(x, T)
            if deps:
                groups = [self.group(("OWNS", "", x), own["value"])]
                for dsys, path in deps:
                    groups.append(sorted({s for (a, b) in path for s in self.group(("DEPENDS_ON", "", f"{a}>{b}"), "+")}))
                ents = [d for d, _ in deps]
                for tmpl in ("What breaks if {x} goes down, and who do I tell?",
                             "If {x} has an outage, what is affected and who should I tell?"):
                    self.out[2].append(self.q(2, tmpl.format(x=n[x]), expected_entities=ents, groups=groups,
                                              rel=["DEPENDS_ON", "OWNS", "LEADS"], impact=True))
        # 4 decision trace
        for d in self.world.w["decisions"]:
            rat = self.sg.spans(d["id"], states="rationale")
            if not rat:
                continue
            for tmpl in ("Why did we decide to {t}, and based on what?", "What was the reasoning behind {a}?"):
                txt = tmpl.format(t=d["title"][0].lower() + d["title"][1:], a=d["number"])
                self.out[4].append(self.q(4, txt, expected_entities=[d["id"]], groups=[rat],
                                          rel=["HAS_STATUS", "REPLACES"]))
            for sysid in d.get("affects") or []:
                if "aurora" in d["title"].lower() or "move" in d["title"].lower():
                    self.out[4].append(self.q(4, f"Why is {n.get(sysid, sysid)} on its current setup "
                                                 f"({d['title']})?", expected_entities=[d["id"]], groups=[rat],
                                              rel=["AFFECTS"]))
        # 5 stale fact: resolved changes
        for c in self.world.w["changes"]:
            if c["expected_outcome"] != "resolved" or c["predicate"] not in ("OWNS", "LEADS", "MEMBER_OF"):
                continue
            key = (c["predicate"], c.get("qualifier") or "", c["key"])
            st = self.cg.state(key, T)
            if not st or not c["to"] or st["value"] != c["to"]:
                continue
            k = c["key"]
            if c["predicate"] == "OWNS":
                texts = [f"Who owns {n.get(k, k)} now?", f"Which team currently owns {n.get(k, k)}?"]
                fact = {"subject_id": c["to"], "predicate": "OWNS", "object_id": k}
            elif c["predicate"] == "LEADS":
                texts = [f"Who leads {n.get(k, k)} now?", f"Who is the current lead of {n.get(k, k)}?"]
                fact = {"subject_id": c["to"], "predicate": "LEADS", "object_id": k}
            else:
                texts = [f"Which team is {n.get(k, k)} on now?", f"What is {n.get(k, k)}'s primary team today?"]
                fact = {"subject_id": k, "predicate": "MEMBER_OF", "object_id": c["to"]}
            for txt in texts:
                self.out[5].append(self.q(5, txt, expected_entities=[c["to"]], expected_fact=fact,
                                          groups=[self.group(key, c["to"])],
                                          forbidden=self.stale_spans(key, c["from"], c["at"]),
                                          change_id=c["change_id"], rel=[c["predicate"]]))
        # 6 unanswerable
        fakes = ["Quasar Gateway", "Nimbus Vault", "Orbit Relay", "Helix Cache", "Zephyr Mesh", "Lumen Index"]
        for f in fakes:
            for tmpl in ("Who owns {x}?", "What breaks if {x} goes down?", "Who leads {x}?"):
                self.out[6].append(self.q(6, tmpl.format(x=f), must_abstain=True))
        for x in systems[:6]:
            self.out[6].append(self.q(6, f"What is the uptime SLA of {n[x]} in milliseconds?",
                                      expected_entities=[x], must_abstain=True))
        self.scripted(T)
        result = []
        for cat, qs in sorted(self.out.items()):
            by_label: dict[str, list[dict]] = defaultdict(list)
            for q in qs:
                by_label[label_of(q)].append(q)
            for lab in sorted(by_label):
                xs = by_label[lab]
                if len(xs) > per_cat:
                    xs = sorted(self.rnd.sample(xs, per_cat), key=lambda q: q["id"])
                result += xs
        return result

    # scripted categories: 4-pending, 7, 9, 10
    def scripted(self, T: int) -> None:
        """Questions that need state the seed does not have (A63): each carries a `setup_script`, a list
        of steps the runner executes on an isolated scratch graph before asking. Steps name their result
        with `ref`; `gold_action_refs` are resolved by the runner into `gold_action_ids` (and
        `gold_proposal_ids`, `belief_at`, the `{date}` placeholder) once the script has run. Questions
        that share a script share one scratch graph. Gold still comes only from the declarations."""
        n = self.names
        w = self.world.w
        demo = w.get("demo_identity") or w["people"][0]["id"]
        systems = [s["id"] for s in w["systems"]]

        # 7 past belief: "Why did you route {ticket} to {person} on {date}?" after a seeded routing.
        # Gold target per 03 §1.3: the current owner of what the ticket is ABOUT (inherited through
        # PART_OF when a System has no owner), then that team's current lead. Disputed chains are skipped
        # so the declared recorded value is the only candidate.
        routes: list[dict] = []
        route_q: list[tuple[dict, dict]] = []
        for t in w["tickets"]:
            if not t.get("about_timeline"):
                continue
            x = t["about_timeline"][-1]["about"]
            own = self.cg.state(("OWNS", "", x), T)
            groups = []
            x_owned = x
            if not own and x.startswith("system:"):
                par = self.cg.state(("PART_OF", "", x), T)
                if par:
                    groups.append(self.group(("PART_OF", "", x), par["value"]))
                    own = self.cg.state(("OWNS", "", par["value"]), T)
                    x_owned = par["value"]
            if not own or own["disputes"] or not own["value"].startswith("team:"):
                continue
            team = own["value"]
            groups.append(self.group(("OWNS", "", x_owned), team))
            lead = self.cg.state(("LEADS", "", team), T)
            target = team
            rel = ["ABOUT", "OWNS"]
            if lead and lead["value"] and not lead["disputes"]:
                target = lead["value"]
                groups.append(self.group(("LEADS", "", team), lead["value"]))
                rel.append("LEADS")
            elif lead and lead["disputes"]:
                continue
            ref = f"route:{t['id']}"
            routes.append({"op": "route_to_owner", "ticket": t["id"], "as": demo, "ref": ref})
            route_q.append(({"ticket": t, "target": target, "team": team, "x": x, "groups": groups, "rel": rel,
                             "ref": ref}, own))
        tmpls7 = ["Why did you route {t} to {p} on {date}?",
                  "On {date} you routed {t} to {p}. What was that based on?",
                  "Earlier you routed {t} to {p}. Which facts did you rely on?"]
        for i, (r, own) in enumerate(route_q):
            t = r["ticket"]
            for ti, tmpl in enumerate(tmpls7):
                self.out[7].append(self.q(
                    7, tmpl.format(t=t["key"], p=n.get(r["target"], r["target"]), date="{date}"),
                    expected_entities=[r["target"], r["team"]],
                    expected_fact={"subject_id": r["team"], "predicate": "OWNS", "object_id": r["x"]},
                    groups=r["groups"], rel=r["rel"], setup_script=routes, gold_action_refs=[r["ref"]],
                    belief_at_from_action=True, session="token", acting_as=demo, expected_tense="current",
                    gold_action_ids=[], tmpl=ti))

        # 4 pending: "Is anything pending for {ADR}?" after a seeded draft_adr_supersession. Gold: the
        # proposals that draft produced (resolved by the runner), labelled proposed, citing the action.
        drafts: list[dict] = []
        pending: list[dict] = []
        for d in w["decisions"]:
            st = self.cg.state(("HAS_STATUS", "", d["id"]), T)
            if not st or st["value"].lstrip("=") != "accepted":
                continue
            ref = f"draft:{d['id']}"
            drafts.append({"op": "draft_adr_supersession", "decision": d["id"], "as": demo, "ref": ref,
                           "reason": f"Revisit {d['title']}"})
            pending.append({"d": d, "ref": ref})
        tmpls4 = ["Is anything pending for {a}?", "Are there open proposals against {a}?",
                  "Is there a draft that would supersede {a}?", "What is pending on {a} right now?"]
        for p in pending:
            d = p["d"]
            for ti, tmpl in enumerate(tmpls4):
                self.out[4].append(self.q(
                    4, tmpl.format(a=d["number"]), expected_entities=[d["id"]], groups=[],
                    rel=["REPLACES", "HAS_STATUS"], setup_script=drafts, gold_action_refs=[p["ref"]],
                    expected_tense="proposed", session="token", acting_as=demo, gold_action_ids=[],
                    tag="pending", tmpl=ti))

        # 9 session memory: two turns in one token session. Turn 1 establishes something (a question,
        # or a learn_fact statement); turn 2 depends on it. Gold = turn 1's entities and its span
        # (resolved by the runner from the stored session turn), plus the learn_fact action if any.
        recall_t = ["What did I ask you about earlier?", "Remind me: what was my last question about?",
                    "Earlier in this session, what did I ask about?"]
        learn_t = ["What did you learn from me earlier?", "Earlier I told you a fact. What was it?",
                   "Remind me what I taught you earlier in this session."]
        people = [p["id"] for p in w["people"]]
        teams = [t["id"] for t in w["teams"]]
        projects = [p["id"] for p in w["projects"]]
        for x in systems + projects:
            own = self.cg.state(("OWNS", "", x), T)
            if not own:
                continue
            first = f"Who owns {n[x]}?"
            for ti, tmpl in enumerate(recall_t):
                self.out[9].append(self.q(9, tmpl, expected_entities=[x], groups=[],
                                          rel=[], turns=[first, tmpl], gold_turn_spans=[0],
                                          session="token", acting_as=self.rnd.choice(people), tmpl=ti))
        for team in teams:
            lead = self.cg.state(("LEADS", "", team), T)
            if not lead:
                continue
            first = f"Who leads {n[team]}?"
            for ti, tmpl in enumerate(recall_t):
                self.out[9].append(self.q(9, tmpl, expected_entities=[team], groups=[],
                                          rel=[], turns=[first, tmpl], gold_turn_spans=[0],
                                          session="token", acting_as=self.rnd.choice(people), tmpl=ti))
        for i, x in enumerate(systems):
            own = self.cg.state(("OWNS", "", x), T)
            if not own or own["disputes"] or x in self.anchor_ids:
                continue
            other_teams = [t for t in teams if t != own["value"]]
            if not other_teams:
                continue
            other = other_teams[i % len(other_teams)]
            first = f"{n[other]} owns {n[x]} now"
            for ti, tmpl in enumerate(learn_t):
                self.out[9].append(self.q(9, tmpl, expected_entities=[other, x], groups=[],
                                          rel=["OWNS"], turns=[first, tmpl], gold_turn_spans=[0],
                                          gold_action_from_turn=0, gold_action_ids=[], session="token",
                                          acting_as=demo, tmpl=3 + ti))

        # 10 outside the templates: aggregates and comparisons with a numeric or entity answer from the
        # declarations. Either a correct answer (any label; unverified_path expected) or an abstention is
        # acceptable; the runner reports which.
        owns_by_team: dict[str, set[str]] = defaultdict(set)
        for x in systems:
            own = self.cg.state(("OWNS", "", x), T)
            if own and own["value"].startswith("team:"):
                owns_by_team[own["value"]].add(x)
        direct: dict[str, set[str]] = defaultdict(set)
        for key in list(self.cg.facts):
            if key[0] == "DEPENDS_ON":
                st = self.cg.state(key, T)
                if st and st["value"] == "+":
                    a, b = key[2].split(">")
                    direct[b].add(a)
        members: dict[str, set[str]] = defaultdict(set)
        for p in people:
            st = self.cg.state(("MEMBER_OF", "primary", p), T)
            if st and st["value"]:
                members[st["value"]].add(p)

        def agg(text: str, answer: dict, ents: list[str], rel: list[str]) -> None:
            self.out[10].append(self.q(10, text, expected_entities=ents, groups=[], rel=rel,
                                       expected_answer=answer, acceptable=["correct", "abstain"]))

        for team, xs in sorted(owns_by_team.items()):
            agg(f"How many systems does {n[team]} own?", {"number": len(xs)}, [], ["OWNS"])
            for x in systems:
                k = len({d for d in direct.get(x, set()) if d in xs})
                if k:
                    agg(f"How many systems does {n[team]} own that depend on {n[x]}?", {"number": k}, [],
                        ["OWNS", "DEPENDS_ON"])
        for x in systems:
            if direct.get(x):
                agg(f"How many systems depend directly on {n[x]}?", {"number": len(direct[x])}, [], ["DEPENDS_ON"])
                owners = {self.cg.state(("OWNS", "", d), T)["value"] for d in direct[x]
                          if self.cg.state(("OWNS", "", d), T)}
                agg(f"How many different teams own systems that depend on {n[x]}?", {"number": len(owners)}, [],
                    ["DEPENDS_ON", "OWNS"])

        # Item 17's graph algorithms, with gold from the declarations (the most direct-or-indirect dependents,
        # teams with no lead), not from the algorithms themselves
        def dependents(x: str) -> set[str]:
            seen: set[str] = set()
            stack = [x]
            while stack:
                for d in direct.get(stack.pop(), set()) - seen:
                    seen.add(d)
                    stack.append(d)
            return seen
        top = sorted(systems, key=lambda x: (-len(dependents(x)), n[x]))[0]
        algo: list[tuple[str, str, list[str]]] = []
        if dependents(top):
            algo.append(("Which systems are most critical, with the most systems depending on them directly or "
                         "indirectly?", top, ["DEPENDS_ON"]))
        leaderless = [x["id"] for x in self.world.w["teams"] if not self.cg.state(("LEADS", "", x["id"]), T)]
        if leaderless:
            algo.append(("Which teams have no lead right now?", sorted(leaderless)[0], ["LEADS"]))
        for text, gold, rel in algo:   # category 11: few enough to be asked every run, never sampled away
            self.out[11].append(self.q(11, text, expected_entities=[gold], groups=[], rel=rel,
                                       expected_answer={"entity": gold}, acceptable=["correct", "abstain"]))

        # Systems belonging to projects
        parts_by_proj: dict[str, set[str]] = defaultdict(set)
        for x in systems:
            st = self.cg.state(("PART_OF", "", x), T)
            if st and st["value"]:
                parts_by_proj[st["value"]].add(x)
        for p, xs in sorted(parts_by_proj.items()):
            agg(f"How many systems belong to {n.get(p, p)}?", {"number": len(xs)}, [p], ["PART_OF"])
            agg(f"How many systems are part of {n.get(p, p)}?", {"number": len(xs)}, [p], ["PART_OF"])

        # Dependencies outgoing from systems
        dep_from: dict[str, set[str]] = defaultdict(set)
        for key in list(self.cg.facts):
            if key[0] == "DEPENDS_ON":
                st = self.cg.state(key, T)
                if st and st["value"] == "+":
                    a, b = key[2].split(">")
                    dep_from[a].add(b)
        for x in systems:
            if dep_from.get(x):
                agg(f"How many systems does {n[x]} depend on?", {"number": len(dep_from[x])}, [x], ["DEPENDS_ON"])

        # Decisions affecting systems
        for x in systems:
            affects_x = len([d for d in w["decisions"] if x in (d.get("affects") or [])])
            if affects_x:
                agg(f"How many architecture decisions affect {n[x]}?", {"number": affects_x}, [x], ["AFFECTS"])

        def unique_max(m: dict[str, set[str]]) -> str | None:
            if not m:
                return None
            best = sorted(m.items(), key=lambda kv: -len(kv[1]))
            return best[0][0] if len(best) == 1 or len(best[0][1]) > len(best[1][1]) else None

        top = unique_max(owns_by_team)
        if top:
            for tmpl in ("Which team owns the most systems?", "Which team is responsible for the largest number of systems?"):
                agg(tmpl, {"entity": top}, [top], ["OWNS"])
        top = unique_max(members)
        if top:
            for tmpl in ("Which team has the most people?", "Which team has the largest primary membership?"):
                agg(tmpl, {"entity": top}, [top], ["MEMBER_OF"])
        top = unique_max(direct)
        if top:
            for tmpl in ("Which system has the most direct dependents?", "Which system do the most other systems depend on?"):
                agg(tmpl, {"entity": top}, [top], ["DEPENDS_ON"])
        top_proj = unique_max(parts_by_proj)
        if top_proj:
            agg("Which project contains the most systems?", {"entity": top_proj}, [top_proj], ["PART_OF"])
        for team, ps in sorted(members.items()):
            agg(f"How many people are primary members of {n[team]}?", {"number": len(ps)}, [], ["MEMBER_OF"])


    def _dependents(self, x: str, V: int) -> list[tuple[str, list[tuple[str, str]]]]:
        deps = defaultdict(set)
        for key, cs in list(self.cg.facts.items()):
            if key[0] != "DEPENDS_ON":
                continue
            st = self.cg.state(key, V)
            if st and st["value"] == "+":
                a, b = key[2].split(">")
                deps[b].add(a)
        out, frontier, seen = [], [(x, [])], {x}
        for _ in range(3):
            nxt = []
            for node, path in frontier:
                for d in sorted(deps.get(node, [])):
                    if d in seen:
                        continue
                    seen.add(d)
                    p2 = path + [(d, node)]
                    out.append((d, p2))
                    nxt.append((d, p2))
            frontier = nxt
        return out


def label_of(q: dict) -> str:
    """Category label for sampling and tables: the category number plus a tag (e.g. '4-pending')."""
    return f"{q['category']}-{q['tag']}" if q.get("tag") else str(q["category"])
