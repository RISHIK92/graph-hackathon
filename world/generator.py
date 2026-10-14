"""Seeded synthetic world generator (05 §3.1–3.4).

Pipeline for one seed (`build_seed`):

1. Load `anchor.yaml` and merge it first (05 §3.4).
2. Generate the random world around it: people, teams, projects, systems, the systems-of-record
   timeline (roster + catalogue), prose-only truths, decisions, tickets, prose documents and
   every distractor of 05 §3.2. Anchor entities are never given random distractors.
3. Derive `changes[]` from the timeline (every change of every chain) and merge the authored
   declarations (anchor, disputes). Build the true timeline `facts[]`.
4. Render every document (`world.render`) sentence by sentence, then attach `fact:`/`change:`
   refs to each stating sentence, list each change's statements with their ranks, and declare
   `stale_docs`.
5. Run the generator checks (`world.checks`); any failure raises `GenerationError`.

Internal representation (not part of the on-disk contract):
- timeline interval: {p, q, s, o, v, from, to, src}; `src` = record (roster/catalogue) | prose.
- claim: {p, q, s, o, v, neg, date}; `date` = stated date or None.
- sentence: {text, claims, hedge}.
"""
from __future__ import annotations

import random
from collections import defaultdict
from pathlib import Path

import yaml

from brain import registry
from brain.ids import doc_key as mk_doc_key
from world.common import (DAY, MAX, GenerationError, chain_of, claim_chain, claim_value, iso,
                          is_functional, slug, to_ms, value_of)

HERE = Path(__file__).resolve().parent
ANCHOR_PATH = HERE / "anchor.yaml"

COMPANY = "Quillfeather Finance"
START = to_ms("2025-01-01")
TODAY = to_ms("2026-10-01")

TARGETS = dict(people=40, teams=6, projects=10, systems=15, decisions=12, tickets=60, chat=400,
               meetings=12)

# Well-known public figures. Generated names are checked against this list (05 §3.1).
PUBLIC_FIGURES = sorted({
    "elon musk", "bill gates", "jeff bezos", "mark zuckerberg", "tim cook", "sundar pichai",
    "satya nadella", "sam altman", "taylor swift", "barack obama", "joe biden", "donald trump",
    "oprah winfrey", "lionel messi", "cristiano ronaldo", "serena williams", "lebron james",
    "greta thunberg", "isaac newton", "rafael nadal", "ingrid bergman", "hugo boss",
    "mads mikkelsen", "lars ulrich", "kai havertz", "hugo lloris", "felix kjellberg",
    "yusuf islam", "zane lowe", "lars von trier", "uma thurman", "rhea seehorn",
    "nikhil kamath", "maya angelou", "esme creed", "selin sayek", "valeria golino",
    "kenji sato", "rohan bopanna", "darius rucker", "noor jehan", "amara la negra",
    "talia shire", "isaac hayes", "chiara ferragni", "joaquin phoenix", "rafael benitez",
})

FIRST_NAMES = [
    "Aiko", "Amara", "Anders", "Beatriz", "Callum", "Chiara", "Dalia", "Darius", "Elif", "Emeka",
    "Farah", "Felix", "Greta", "Hamid", "Hana", "Ilse", "Isaac", "Jada", "Joaquin", "Kai",
    "Kalinda", "Lars", "Leila", "Lorenzo", "Mads", "Maya", "Mirela", "Nadia", "Nikhil", "Noor",
    "Oskar", "Paloma", "Quentin", "Rafael", "Rhea", "Rohan", "Saanvi", "Sam", "Selin", "Soren",
    "Talia", "Teodor", "Uma", "Valeria", "Wren", "Yara", "Yusuf", "Zane", "Zofia", "Arjun",
    "Bianca", "Cyrus", "Dmitri", "Esme", "Femi", "Gideon", "Hugo", "Ingrid", "Jules", "Kenji",
]
LAST_NAMES = [
    "Abernathy", "Achebe", "Bergstrom", "Castellanos", "Dahl", "Ekwueme", "Ferreira", "Galloway",
    "Haddad", "Ishikawa", "Jaramillo", "Kowal", "Lindgren", "Mbatha", "Nakamura", "Okafor",
    "Petrov", "Quiroga", "Rasmussen", "Sandoval", "Takahashi", "Udeh", "Varga", "Whitfield",
    "Xu", "Yilmaz", "Zielinski", "Albescu", "Brennan", "Chaudhry", "Delacroix", "Esposito",
    "Fontaine", "Gunnarsson", "Holloway", "Iyer", "Jovanovic", "Kariuki", "Laine", "Moreau",
    "Novak", "Oyelaran", "Pellegrino", "Quint", "Rosales", "Sato", "Thorne", "Ueda", "Vasquez",
    "Wexler", "Yoon", "Zamora", "Arnesen", "Blackwood", "Carrow", "Dunmore", "Grimaldi", "Hartley",
]
TEAM_POOL = [("Growth", "GRO"), ("Mobile", "MOB"), ("Risk", "RSK"), ("Insights", "INS"),
             ("Fulfilment", "FUL"), ("Messaging", "MSG"), ("Onboarding", "ONB"), ("Commerce", "COM")]
SYSTEM_POOL = ["Notifications", "Search Index", "Fraud Scoring", "Feature Flags", "Auth Gateway",
               "Pricing Engine", "Rate Limiter", "Event Bus", "Audit Log", "Session Store",
               "Geo Lookup", "Email Relay", "Image Resizer", "Webhook Dispatcher"]
NEAR_DUP_SYSTEMS = ["Billing", "Billing-v2"]
PROJECT_POOL = ["Merchant Portal", "Wallet Launch", "Chargeback Defense", "Discovery Revamp",
                "Partner API", "Loyalty Rewards", "Data Warehouse", "Account Recovery",
                "Instant Payouts", "Smart Routing", "Store Locator", "Gift Cards"]
TECH_POOL = ["Kafka", "Redis", "gRPC", "OpenTelemetry", "Terraform", "Kubernetes", "DynamoDB",
             "Elasticsearch", "Envoy", "Temporal", "ClickHouse", "NATS"]
TITLES = ["Software Engineer", "Senior Software Engineer", "Staff Engineer",
          "Site Reliability Engineer", "Data Engineer", "Product Manager", "QA Engineer"]

FORM_OF_DISPUTE = {"chat_contradiction": "chat", "su_chat": "chat", "edit_below": "prose",
                   "equal": "prose", "su_prose": "prose"}


# normalisation

def _src_for(p: str, o: str) -> str:
    if p == "WORKS_ON" or (p == "LEADS" and o.startswith("project:")):
        return "prose"
    return "record"


def norm_interval(d: dict) -> dict:
    p, o = d["p"], d.get("o", "") or ""
    return {"p": p, "q": d.get("q", "") or "", "s": d["s"], "o": o, "v": d.get("v", "") or "",
            "from": to_ms(d["from"]), "to": to_ms(d.get("to")), "src": d.get("src") or _src_for(p, o)}


def norm_claim(c: dict) -> dict:
    return {"p": c["p"], "q": c.get("q", "") or "", "s": c["s"], "o": c.get("o", "") or "",
            "v": c.get("v", "") or "", "neg": bool(c.get("neg", False)),
            "date": to_ms(c["date"]) if c.get("date") is not None else None}


def norm_sentence(x) -> dict:
    if isinstance(x, str):
        return {"text": x, "claims": [], "hedge": False}
    return {"text": x["text"], "claims": [norm_claim(c) for c in x.get("claims", [])],
            "hedge": bool(x.get("hedge", False))}


def norm_doc(d: dict) -> dict:
    kind = d["kind"]
    base = {"kind": kind, "author": d.get("author"), "distractors": list(d.get("distractors", []))}
    if kind == "wiki":
        base.update(external_id=d["slug"], doc_key=mk_doc_key("wiki", "confluence", d["slug"]),
                    title=d["title"],
                    revisions=[{"updated_at": to_ms(r["updated_at"]),
                                "paragraphs": [[norm_sentence(s) for s in para] for para in r["paragraphs"]]}
                               for r in d["revisions"]])
    elif kind == "meeting":
        base.update(external_id=d["slug"], doc_key=mk_doc_key("meeting", "notes", d["slug"]),
                    title=d["title"], attendees=list(d["attendees"]),
                    revisions=[{"updated_at": to_ms(d["date"]),
                                "paragraphs": [[norm_sentence(s) for s in para] for para in d["paragraphs"]]}])
    elif kind == "chat":
        ts = to_ms(d["ts"])
        base.update(channel=d["channel"], ts=ts, external_id=f"{d['channel']}/{ts}",
                    doc_key=mk_doc_key("chat", "slack", f"{d['channel']}/{ts}"),
                    title=f"#{d['channel']} message", thread=d.get("thread"),
                    thread_ts=d.get("thread_ts"),
                    revisions=[{"updated_at": ts, "paragraphs": [[norm_sentence(s) for s in d["sentences"]]]}])
    else:
        raise GenerationError(f"unknown prose doc kind {kind}")
    return base


def norm_decision(d: dict) -> dict:
    st = [{"status": s["status"], "at": to_ms(s["at"])} for s in d["status_timeline"]]
    return {"id": d["id"], "number": d["number"], "title": d["title"], "date": st[0]["at"],
            "status_timeline": st, "deciders": list(d["deciders"]), "affects": list(d["affects"]),
            "replaces": list(d.get("replaces", [])), "rationale_points": list(d["rationale_points"]),
            "decision_text": d["decision_text"], "consequences": d["consequences"]}


def norm_ticket(t: dict) -> dict:
    return {"key": t["key"], "id": "ticket:" + t["key"].lower(), "title": t["title"],
            "description": t["description"], "created_by": t.get("created_by"),
            "about_timeline": [{"about": a["about"], "at": to_ms(a["at"])} for a in t["about_timeline"]],
            "assignee_timeline": [{"who": a["who"], "at": to_ms(a["at"])} for a in t["assignee_timeline"]],
            "state_timeline": [{"state": a["state"], "at": to_ms(a["at"])} for a in t["state_timeline"]],
            "comments": [{"author": c["author"], "at": to_ms(c["at"]),
                          "sentences": [norm_sentence(s) for s in c["sentences"]]} for c in t.get("comments", [])],
            "distractors": list(t.get("distractors", []))}


def norm_change(c: dict) -> dict:
    return {"change_id": c["change_id"], "predicate": c["predicate"], "qualifier": c.get("qualifier", "") or "",
            "key": c["key"], "from": c["from"], "to": c["to"], "at": to_ms(c["at"]), "true": bool(c["true"]),
            "expected_outcome": c["expected_outcome"], "challenger_correct": c.get("challenger_correct"),
            "stale_docs": c.get("stale_docs"), "tags": list(c.get("tags", []))}


def iv_chain(iv: dict) -> tuple[str, str, str]:
    return chain_of(iv["p"], iv["q"], iv["s"], iv["o"])


def iv_value(iv: dict) -> str:
    return value_of(iv["p"], iv["q"], iv["s"], iv["o"], iv["v"], False)


# the world

class World:
    """Everything the generator knows about one seed, before rendering."""

    def __init__(self, seed: int):
        self.seed = seed
        self.company = {"name": COMPANY, "start_date": START, "end_date": TODAY, "today": TODAY}
        self.D_transfer = 0
        self.D_reorg = 0
        self.demo_identity = ""
        self.anchor_ids: dict = {}
        self.anchor_entities: set[str] = set()
        self.people: list[dict] = []
        self.teams: list[dict] = []
        self.projects: list[dict] = []
        self.systems: list[dict] = []
        self.timeline: list[dict] = []
        self.decisions: list[dict] = []
        self.tickets: list[dict] = []
        self.docs: list[dict] = []
        self.declared: list[dict] = []
        self.change_tags: dict[tuple, list[str]] = defaultdict(list)
        self.reserved: set[tuple] = set()
        self.near_dup_pairs: list[list[str]] = []
        self.team_prefix: dict[str, str] = {}

    # entity lookup
    def entities(self) -> list[dict]:
        return self.people + self.teams + self.projects + self.systems

    def ent(self, eid: str) -> dict:
        for e in self.entities():
            if e["id"] == eid:
                return e
        for d in self.decisions:
            if d["id"] == eid:
                return {"id": d["id"], "name": d["number"], "aliases": []}
        for t in self.tickets:
            if t["id"] == eid:
                return {"id": t["id"], "name": t["key"], "aliases": []}
        raise KeyError(eid)

    # timeline queries (gold == record/prose truth before disputes)
    def all_intervals(self) -> list[dict]:
        out = [dict(iv) for iv in self.timeline]
        for d in self.decisions:
            st = d["status_timeline"]
            for i, s in enumerate(st):
                end = st[i + 1]["at"] if i + 1 < len(st) else MAX
                out.append({"p": "HAS_STATUS", "q": "", "s": d["id"], "o": "", "v": s["status"],
                            "from": s["at"], "to": end, "src": "adr"})
            for who in d["deciders"]:
                out.append({"p": "DECIDED_BY", "q": "", "s": d["id"], "o": who, "v": "", "from": d["date"], "to": MAX, "src": "adr"})
            for a in d["affects"]:
                out.append({"p": "AFFECTS", "q": "", "s": d["id"], "o": a, "v": "", "from": d["date"], "to": MAX, "src": "adr"})
            for r in d["replaces"]:
                out.append({"p": "REPLACES", "q": "", "s": d["id"], "o": r, "v": "", "from": d["date"], "to": MAX, "src": "adr"})
        for t in self.tickets:
            for field, p, valkey in (("about_timeline", "ABOUT", "about"), ("assignee_timeline", "ASSIGNED_TO", "who"),
                                     ("state_timeline", "HAS_STATE", "state")):
                tl = t[field]
                for i, e in enumerate(tl):
                    end = tl[i + 1]["at"] if i + 1 < len(tl) else MAX
                    o, v = (e[valkey], "") if p != "HAS_STATE" else ("", e[valkey])
                    out.append({"p": p, "q": "", "s": t["id"], "o": o, "v": v, "from": e["at"], "to": end, "src": "ticket"})
        return out

    def active(self, p: str, q: str = "", s: str | None = None, o: str | None = None, t: int = 0) -> list[dict]:
        return [iv for iv in self.timeline if iv["p"] == p and iv["q"] == q
                and (s is None or iv["s"] == s) and (o is None or iv["o"] == o)
                and iv["from"] <= t < iv["to"]]

    def owner_at(self, eid: str, t: int) -> str | None:
        a = self.active("OWNS", o=eid, t=t)
        return a[0]["s"] if a else None

    def lead_at(self, oid: str, t: int) -> str | None:
        a = self.active("LEADS", o=oid, t=t)
        return a[0]["s"] if a else None

    def primary_at(self, pid: str, t: int) -> str | None:
        a = self.active("MEMBER_OF", "primary", s=pid, t=t)
        return a[0]["o"] if a else None

    def members_at(self, tid: str, t: int) -> list[str]:
        return sorted(iv["s"] for iv in self.active("MEMBER_OF", "primary", o=tid, t=t))

    def project_at(self, sid: str, t: int) -> str | None:
        a = self.active("PART_OF", s=sid, t=t)
        return a[0]["o"] if a else None

    def deps_at(self, sid: str, t: int) -> list[str]:
        return sorted(iv["o"] for iv in self.active("DEPENDS_ON", s=sid, t=t))

    def set_functional(self, p: str, q: str, key: str, new_val: str, at: int) -> None:
        """Close the chain's interval active at `at` and open `new_val` from `at`."""
        hits = [iv for iv in self.timeline if iv_chain(iv) == (p, q, key) and iv["from"] <= at < iv["to"]]
        if len(hits) != 1:
            raise GenerationError(f"set_functional: {p} {key} has {len(hits)} intervals at {iso(at)}")
        iv = hits[0]
        old_to = iv["to"]
        iv["to"] = at
        new = dict(iv)
        new["from"], new["to"] = at, old_to
        side = registry.get(p, q).key_side
        if side == "object":
            new["s"] = new_val
        elif new_val.count(":"):
            new["o"] = new_val
        else:
            new["v"] = new_val
        self.timeline.append(new)
        if iv["from"] == at:
            self.timeline.remove(iv)


def load_anchor(path: Path = ANCHOR_PATH) -> dict:
    return yaml.safe_load(path.read_text())


def merge_anchor(W: World, A: dict) -> None:
    W.D_transfer = to_ms(A["D_transfer"])
    W.D_reorg = to_ms(A["D_reorg"])
    W.demo_identity = A["demo_identity"]
    W.anchor_ids = dict(A["ids"])
    W.people = [dict(p, aliases=list(p.get("aliases", []))) for p in A["people"]]
    W.teams = [dict(t, aliases=list(t.get("aliases", []))) for t in A["teams"]]
    W.projects = [dict(p, aliases=list(p.get("aliases", []))) for p in A["projects"]]
    W.systems = [dict(s, aliases=list(s.get("aliases", []))) for s in A["systems"]]
    W.timeline = [norm_interval(iv) for iv in A["timeline"]]
    W.decisions = [norm_decision(d) for d in A["decisions"]]
    W.tickets = [norm_ticket(t) for t in A["tickets"]]
    W.docs = [norm_doc(d) for d in A["docs"]]
    W.declared = [norm_change(c) for c in A["changes"]]
    W.anchor_entities = {e["id"] for e in W.entities()} | {d["id"] for d in W.decisions} | {t["id"] for t in W.tickets}
    for c in W.declared:
        W.reserved.add((c["predicate"], c["qualifier"], c["key"]))
    # G4: Ledger's OWNS chain is reserved from every random distractor.
    W.reserved.add(("OWNS", "", W.anchor_ids["ledger"]))
    for tid in W.anchor_entities:
        if tid.startswith("team:"):
            W.team_prefix[tid] = "RDS"


# random world

class Generator:
    def __init__(self, seed: int, anchor: dict | None = None):
        self.seed = seed
        self.rng = random.Random(f"world-{seed}")
        self.W = World(seed)
        merge_anchor(self.W, anchor if anchor is not None else load_anchor())
        self.gen_teams: list[str] = []
        self.gen_systems: list[str] = []
        self.gen_projects: list[str] = []
        self.owns_pool: list[tuple] = []
        self.project_page_at: dict[str, int] = {}
        self.works_on: list[dict] = []
        self.movers: set[str] = set()
        self.dup_people: list[str] = []
        self.chat_used: dict[str, set[int]] = defaultdict(set)
        for d in self.W.docs:
            if d["kind"] == "chat":
                self.chat_used[d["channel"]].add(d["ts"])

    # small helpers
    def rand_day(self, lo: int, hi: int) -> int:
        lo, hi = lo - lo % DAY, hi - hi % DAY
        if hi < lo:
            raise GenerationError(f"empty date range {iso(lo)}..{iso(hi)}")
        return lo + self.rng.randrange((hi - lo) // DAY + 1) * DAY

    def rand_day_not_reorg(self, lo: int, hi: int) -> int:
        """A day for a change that must not land on D_reorg (G10: everything on D_reorg is the
        rank-4 reorganisation)."""
        for _ in range(100):
            t = self.rand_day(lo, hi)
            if t != self.W.D_reorg:
                return t
        raise GenerationError("cannot avoid D_reorg")

    def rand_ts(self, lo: int, hi: int) -> int:
        day = self.rand_day(lo, hi)
        return day + self.rng.randrange(8 * 3600, 19 * 3600) * 1000 + self.rng.randrange(1000)

    def disp(self, eid: str) -> str:
        """Display form of an entity: its name, sometimes an alias."""
        e = self.W.ent(eid)
        if e["aliases"] and self.rng.random() < 0.25:
            return self.rng.choice(e["aliases"])
        return e["name"]

    def name(self, eid: str) -> str:
        return self.W.ent(eid)["name"]

    def chat_ts(self, channel: str, ts: int) -> int:
        while ts in self.chat_used[channel]:
            ts += 1
        self.chat_used[channel].add(ts)
        return ts

    def add_doc_wiki(self, slug_: str, title: str, author: str, revisions: list[tuple[int, list[list]]],
                     distractors: list[str]) -> dict:
        d = {"kind": "wiki", "external_id": slug_, "doc_key": mk_doc_key("wiki", "confluence", slug_),
             "title": title, "author": author, "distractors": list(distractors),
             "revisions": [{"updated_at": t, "paragraphs": paras} for t, paras in revisions]}
        if any(x["doc_key"] == d["doc_key"] for x in self.W.docs):
            raise GenerationError(f"duplicate doc {d['doc_key']}")
        self.W.docs.append(d)
        return d

    def add_doc_meeting(self, slug_: str, title: str, date: int, author: str, attendees: list[str],
                        paragraphs: list[list], distractors: list[str]) -> dict:
        base = slug_
        n = 2
        while any(x["doc_key"] == mk_doc_key("meeting", "notes", slug_) for x in self.W.docs):
            slug_ = f"{base}-{n}"
            n += 1
        d = {"kind": "meeting", "external_id": slug_, "doc_key": mk_doc_key("meeting", "notes", slug_),
             "title": title, "author": author, "attendees": attendees, "distractors": list(distractors),
             "revisions": [{"updated_at": date, "paragraphs": paragraphs}]}
        self.W.docs.append(d)
        return d

    def add_chat(self, channel: str, ts: int, author: str, sentences: list[dict], distractors=(),
                 thread_ts: int | None = None) -> dict:
        ts = self.chat_ts(channel, ts)
        d = {"kind": "chat", "channel": channel, "ts": ts, "external_id": f"{channel}/{ts}",
             "doc_key": mk_doc_key("chat", "slack", f"{channel}/{ts}"), "title": f"#{channel} message",
             "author": author, "distractors": list(distractors), "thread": None, "thread_ts": thread_ts,
             "revisions": [{"updated_at": ts, "paragraphs": [sentences]}]}
        self.W.docs.append(d)
        return d

    @staticmethod
    def S(text: str, *claims: dict) -> dict:
        return {"text": text, "claims": list(claims), "hedge": False}

    @staticmethod
    def C(p: str, s: str, o: str = "", v: str = "", q: str = "", neg: bool = False, date: int | None = None) -> dict:
        return {"p": p, "q": q, "s": s, "o": o, "v": v, "neg": neg, "date": date}

    def team_channel(self, tid: str) -> str:
        return slug(self.name(tid))

    # generation steps
    def run(self) -> World:
        self.gen_people_and_org()
        self.gen_catalogue()
        self.gen_reorg()
        self.gen_ownership_changes()
        self.gen_gap()
        self.gen_secondary_memberships()
        self.gen_dependency_drops()
        self.gen_project_leads()
        self.gen_disputes()
        self.gen_decisions()
        self.gen_tickets()
        self.gen_generic_wiki()
        self.gen_generic_meetings()
        self.gen_chat()
        self.resolve_threads()
        return self.W

    def mk_person(self, name: str, aliases: list[str]) -> dict:
        if name.lower() in PUBLIC_FIGURES:
            raise GenerationError(f"public figure name {name}")
        pid = "person:" + slug(name)
        if any(p["id"] == pid for p in self.W.people):
            raise GenerationError(f"duplicate person id {pid}")
        p = {"id": pid, "name": name, "aliases": aliases, "title": self.rng.choice(TITLES)}
        self.W.people.append(p)
        return p

    def gen_people_and_org(self) -> None:
        W, rng = self.W, self.rng
        used_first = {p["name"].split()[0].lower() for p in W.people}
        firsts = [f for f in FIRST_NAMES if f.lower() not in used_first]
        lasts = list(LAST_NAMES)
        rng.shuffle(firsts)
        rng.shuffle(lasts)
        n_new = TARGETS["people"] - len(W.people)
        # near_dup_name: two people sharing a first name, told apart by alias
        dup_first = firsts.pop()
        l1 = lasts.pop()
        l2 = next(x for x in lasts if x[0] != l1[0])
        lasts.remove(l2)
        pair = [self.mk_person(f"{dup_first} {l}", [f"{dup_first} {l[0]}."])["id"] for l in (l1, l2)]
        self.dup_people = pair
        W.near_dup_pairs.append(list(pair))
        others = []
        while len(others) + 2 < n_new:
            f, l = firsts.pop(), lasts.pop()
            if f"{f} {l}".lower() in PUBLIC_FIGURES:
                continue
            others.append(self.mk_person(f"{f} {l}", [f])["id"])
        # teams
        for name, prefix in rng.sample(TEAM_POOL, TARGETS["teams"] - len(W.teams)):
            tid = "team:" + slug(name)
            W.teams.append({"id": tid, "name": name, "aliases": [slug(name) + "-team"]})
            W.team_prefix[tid] = prefix
            self.gen_teams.append(tid)
        rng.shuffle(others)
        anchor_teams = sorted(t["id"] for t in W.teams if t["id"] in W.anchor_entities)
        k = 0
        for tid in anchor_teams:
            for _ in range(3):
                self._primary(others[k], tid, START)
                k += 1
        rest = others[k:]
        for i, tid in enumerate(self.gen_teams):
            self._primary(rest[i], tid, START)
            W.timeline.append({"p": "LEADS", "q": "", "s": rest[i], "o": tid, "v": "", "from": START, "to": MAX, "src": "record"})
            self._person(rest[i])["title"] = "Engineering Manager"
        for j, pid in enumerate(rest[len(self.gen_teams):]):
            self._primary(pid, self.gen_teams[j % len(self.gen_teams)], START)
        self._primary(pair[0], self.gen_teams[0], START)
        self._primary(pair[1], self.gen_teams[1], START)
        for pid in pair:
            if self._person(pid)["title"] == "Engineering Manager":
                self._person(pid)["title"] = "Software Engineer"

    def _person(self, pid: str) -> dict:
        return next(p for p in self.W.people if p["id"] == pid)

    def _primary(self, pid: str, tid: str, at: int) -> None:
        self.W.timeline.append({"p": "MEMBER_OF", "q": "primary", "s": pid, "o": tid, "v": "", "from": at, "to": MAX, "src": "record"})

    def gen_catalogue(self) -> None:
        W, rng = self.W, self.rng
        for name in rng.sample(PROJECT_POOL, TARGETS["projects"] - len(W.projects)):
            pid = "project:" + slug(name)
            W.projects.append({"id": pid, "name": name, "aliases": [slug(name)]})
            self.gen_projects.append(pid)
        n_sys = TARGETS["systems"] - len(W.systems)
        names = rng.sample(SYSTEM_POOL, n_sys - 2)
        i = rng.randrange(len(names) + 1)
        names.insert(i, "Billing")
        j = rng.randrange(i + 1, len(names) + 1)
        names.insert(j, "Billing-v2")
        for name in names:
            sid = "system:" + slug(name)
            alias = slug(name) + "-svc"
            W.systems.append({"id": sid, "name": name, "aliases": [alias], "tier": rng.choice([1, 2, 2, 3])})
            self.gen_systems.append(sid)
        W.near_dup_pairs.append(["system:billing", "system:billing-v2"])
        teams = list(self.gen_teams)
        rng.shuffle(teams)
        for k, pid in enumerate(self.gen_projects):
            W.timeline.append({"p": "OWNS", "q": "", "s": teams[k % len(teams)], "o": pid, "v": "", "from": START, "to": MAX, "src": "record"})
        rng.shuffle(teams)
        for k, sid in enumerate(self.gen_systems):
            W.timeline.append({"p": "OWNS", "q": "", "s": teams[k % len(teams)], "o": sid, "v": "", "from": START, "to": MAX, "src": "record"})
            W.timeline.append({"p": "PART_OF", "q": "", "s": sid, "o": rng.choice(self.gen_projects), "v": "", "from": START, "to": MAX, "src": "record"})
        edges = set()
        for k, sid in enumerate(self.gen_systems):
            earlier = self.gen_systems[:k]
            if sid == "system:billing-v2":
                edges.add((sid, "system:billing"))
            for o in rng.sample(earlier, min(len(earlier), rng.choice([0, 1, 1, 2]))):
                edges.add((sid, o))
        while len(edges) < 5:
            a, b = sorted(rng.sample(range(len(self.gen_systems)), 2))
            edges.add((self.gen_systems[b], self.gen_systems[a]))
        for s, o in sorted(edges):
            W.timeline.append({"p": "DEPENDS_ON", "q": "", "s": s, "o": o, "v": "", "from": START, "to": MAX, "src": "record"})
        self.owns_pool = [("OWNS", "", x) for x in self.gen_systems + self.gen_projects]
        rng.shuffle(self.owns_pool)

    def take_owns(self, kind: str | None = None) -> str:
        for ch in self.owns_pool:
            if kind is None or ch[2].startswith(kind + ":"):
                self.owns_pool.remove(ch)
                return ch[2]
        raise GenerationError(f"no free OWNS chain left for {kind or 'any'} (world too small)")

    def other_team(self, not_this: str | None) -> str:
        return self.rng.choice([t for t in self.gen_teams if t != not_this])

    def gen_reorg(self) -> None:
        """G10 (generated part): LEADS, primary MEMBER_OF, OWNS and PART_OF moves on D_reorg."""
        W, rng, D = self.W, self.rng, self.W.D_reorg
        A = rng.choice(self.gen_teams)
        C = self.other_team(A)
        cands = [p for p in W.members_at(C, D) if p != W.lead_at(C, D) and p not in self.dup_people]
        m = rng.choice(cands)
        W.set_functional("MEMBER_OF", "primary", m, A, D)
        W.set_functional("LEADS", "", A, m, D)
        self._person(m)["title"] = "Engineering Manager"
        self.movers.add(m)
        self.lead_change_team = A
        for _ in range(2):
            src = rng.choice(self.gen_teams)
            cands = [p for p in W.members_at(src, D) if p != W.lead_at(src, D)
                     and p not in self.dup_people and p not in self.movers]
            p = rng.choice(cands)
            W.set_functional("MEMBER_OF", "primary", p, self.other_team(src), D)
            self.movers.add(p)
        for _ in range(2):
            sid = self.take_owns("system")
            W.set_functional("OWNS", "", sid, self.other_team(W.owner_at(sid, D)), D)
        sid = rng.choice(self.gen_systems)
        cur = W.project_at(sid, D)
        W.set_functional("PART_OF", "", sid, rng.choice([p for p in self.gen_projects if p != cur]), D)

    def gen_ownership_changes(self) -> None:
        """stale_doc / stale_resolved, edited_doc, and a plain project ownership change."""
        W = self.W
        lo, hi = to_ms("2025-05-01"), to_ms("2026-08-15")
        for _ in range(2):
            sid = self.take_owns("system")
            t_c = self.rand_day_not_reorg(lo, hi)
            X = W.owner_at(sid, t_c - DAY)
            W.set_functional("OWNS", "", sid, self.other_team(X), t_c)
            t_a = self.rand_day(START + 20 * DAY, t_c - 20 * DAY)
            author = self.rng.choice(W.members_at(X, t_a))
            self.add_doc_wiki(slug(self.name(sid)) + "-runbook", f"{self.name(sid)} runbook", author,
                              [(t_a, [[self.S(f"This page collects the on-call steps for {self.disp(sid)}."),
                                       self.S(f"{self.disp(X)} owns {self.disp(sid)}.", self.C("OWNS", X, sid))],
                                      [self.S("Escalate through the on-call rota before paging anyone directly.")]])],
                              ["stale_doc"])
            W.change_tags[("OWNS", "", sid, t_c)].append("stale_resolved")
        sid = self.take_owns("system")
        t_c = self.rand_day_not_reorg(lo, hi)
        X = W.owner_at(sid, t_c - DAY)
        Y = self.other_team(X)
        W.set_functional("OWNS", "", sid, Y, t_c)
        t_a = self.rand_day(START + 20 * DAY, t_c - 20 * DAY)
        t_e = self.rand_day(t_c, min(t_c + 40 * DAY, TODAY - DAY))
        author = self.rng.choice(W.members_at(X, t_a))
        nm = self.name(sid)
        self.add_doc_wiki(slug(nm) + "-oncall", f"{nm} on-call guide", author, [
            (t_a, [[self.S(f"{self.disp(X)} owns {self.disp(sid)}.", self.C("OWNS", X, sid))],
                   [self.S(f"Dashboards for {nm} live in the shared observability folder.")]]),
            (t_e, [[self.S(f"Since {iso(t_c)}, {self.disp(Y)} owns {self.disp(sid)}.", self.C("OWNS", Y, sid, date=t_c))],
                   [self.S(f"Dashboards for {nm} live in the shared observability folder.")]]),
        ], ["edited_doc"])
        W.change_tags[("OWNS", "", sid, t_c)].append("edited_doc")
        pid = self.take_owns("project")
        t_c = self.rand_day_not_reorg(lo, hi)
        W.set_functional("OWNS", "", pid, self.other_team(W.owner_at(pid, t_c - DAY)), t_c)

    def gen_gap(self) -> None:
        """fallback_gap: an owner team loses its lead (roster row becomes `member`)."""
        W = self.W
        cands = [t for t in self.gen_teams if t != self.lead_change_team
                 and any(W.owner_at(s, TODAY - DAY) == t for s in self.gen_systems)]
        if not cands:
            raise GenerationError("no team can host the fallback_gap")
        B = self.rng.choice(cands)
        t_gap = self.rand_day_not_reorg(W.D_reorg + 30 * DAY, TODAY - 30 * DAY)
        iv = W.active("LEADS", o=B, t=t_gap)[0]
        iv["to"] = t_gap
        W.reserved.add(("LEADS", "", B))
        W.change_tags[("LEADS", "", B, t_gap)].append("fallback_gap")
        self.gap_team = B

    def gen_secondary_memberships(self) -> None:
        W = self.W
        cands = [p["id"] for p in W.people if p["id"] not in W.anchor_entities and p["id"] not in self.movers
                 and p["id"] not in self.dup_people and W.primary_at(p["id"], START) in self.gen_teams
                 and not W.active("LEADS", s=p["id"], t=START)]
        for pid in self.rng.sample(cands, 4):
            prim = W.primary_at(pid, START)
            tid = self.other_team(prim)
            W.timeline.append({"p": "MEMBER_OF", "q": "", "s": pid, "o": tid, "v": "",
                               "from": self.rand_day(START + 30 * DAY, START + 300 * DAY), "to": MAX, "src": "record"})

    def gen_dependency_drops(self) -> None:
        """Dependency closures, each also stated by a `negation` sentence in a meeting note."""
        W = self.W
        edges = [iv for iv in W.timeline if iv["p"] == "DEPENDS_ON" and iv["s"] in self.gen_systems and iv["to"] == MAX]
        for iv in self.rng.sample(edges, 2):
            t_d = self.rand_day(to_ms("2025-04-01"), to_ms("2026-08-01"))
            iv["to"] = t_d
            s, o = iv["s"], iv["o"]
            W.change_tags[("DEPENDS_ON", "", f"{s}>{o}", t_d)].append("negation")
            owner = W.owner_at(s, t_d)
            att = W.members_at(owner, t_d)[:4]
            date = self.rand_day(t_d + DAY, t_d + 21 * DAY)
            self.add_doc_meeting(f"{slug(self.name(s))}-architecture-sync", f"{self.name(s)} architecture sync",
                                 date, att[0], att,
                                 [[self.S(f"We reviewed the call graph of {self.disp(s)}."),
                                   self.S(f"On {iso(t_d)}, we dropped the dependency on {self.disp(o)} from {self.disp(s)}.",
                                          self.C("DEPENDS_ON", s, o, neg=True, date=t_d))],
                                  [self.S("Action items are tracked in the team board.")]],
                                 ["negation"])

    def gen_project_leads(self) -> None:
        """Prose-only project LEADS chains; two change at rank 2 (stale_resolved via prose edits)."""
        W = self.W
        for pid in self.gen_projects:
            owner = W.owner_at(pid, START)
            lead = self.rng.choice(W.members_at(owner, START))
            W.timeline.append({"p": "LEADS", "q": "", "s": lead, "o": pid, "v": "", "from": START, "to": MAX, "src": "prose"})
            self.project_page_at[pid] = self.rand_day(START + 15 * DAY, START + 200 * DAY)
        self.lead_pool = list(self.gen_projects)
        self.rng.shuffle(self.lead_pool)
        for _ in range(2):
            pid = self.lead_pool.pop()
            t_b = self.rand_day_not_reorg(self.project_page_at[pid] + 40 * DAY, TODAY - 20 * DAY)
            old = W.lead_at(pid, t_b)
            owner = W.owner_at(pid, t_b)
            new = self.rng.choice([p for p in W.members_at(owner, t_b) + W.members_at(self.other_team(owner), t_b) if p != old])
            W.set_functional("LEADS", "", pid, new, t_b)
            W.change_tags[("LEADS", "", pid, t_b)].append("stale_resolved")
            self.add_doc_meeting(f"{slug(self.name(pid))}-kickoff", f"{self.name(pid)} kickoff", t_b, new,
                                 sorted({new, old} | set(W.members_at(owner, t_b)[:2])),
                                 [[self.S(f"Since {iso(t_b)}, {self.disp(new)} leads {self.disp(pid)}.",
                                          self.C("LEADS", new, pid, date=t_b)),
                                   self.S("The team agreed to revisit the roadmap in six weeks.")]], [])
        # WORKS_ON truths (prose only), stated later in generic meetings
        pairs = set()
        while len(pairs) < 16:
            pid = self.rng.choice(self.gen_projects)
            person = self.rng.choice(W.members_at(W.owner_at(pid, START), START))
            pairs.add((person, pid))
        for person, pid in sorted(pairs):
            iv = {"p": "WORKS_ON", "q": "", "s": person, "o": pid, "v": "", "from": START, "to": MAX, "src": "prose"}
            W.timeline.append(iv)
            self.works_on.append(iv)

    # disputes and balance (05 §3.1 Balance)
    def gen_disputes(self) -> None:
        W, rng = self.W, self.rng
        counts = {("chat", True): 0, ("chat", False): 0, ("prose", True): 0, ("prose", False): 0}
        for c in W.declared:
            if c["expected_outcome"] == "disputed":
                form = "chat" if "chat_contradiction" in c["tags"] or "su_chat" in c["tags"] else "prose"
                counts[(form, bool(c["challenger_correct"]))] += 1
        plan = {"chat": ["chat_contradiction"] * rng.randint(2, 3) + ["su_chat"] * rng.randint(1, 2),
                "prose": ["edit_below"] * rng.randint(1, 2) + ["equal"] * rng.randint(1, 2) + ["su_prose"]}
        for form in ("chat", "prose"):
            rng.shuffle(plan[form])
            flag = rng.random() < 0.5
            for kind in plan[form]:
                self.dispute(kind, flag, comp=False)
                counts[(form, flag)] += 1
                flag = not flag
        # compensating cases so that every (form, correctness) cell is equal
        target = max(counts.values())
        alt = 0
        for (form, correct), n in sorted(counts.items()):
            for _ in range(target - n):
                if form == "chat":
                    kind = "chat_contradiction" if self.owns_pool else "su_chat"
                else:
                    kind = ("su_prose", "edit_below")[alt % 2]
                    alt += 1
                self.dispute(kind, correct, comp=True)
                counts[(form, correct)] += 1

    def dispute(self, kind: str, correct: bool, comp: bool) -> None:
        W = self.W
        tags = {"chat_contradiction": ["chat_contradiction"], "su_chat": ["stale_unresolved"],
                "edit_below": ["edit_below_record"], "equal": ["equal_date_dispute"],
                "su_prose": ["stale_unresolved"]}[kind]
        if comp:
            tags = tags + ["balance_compensation"]
        if kind == "su_chat":
            if not self.lead_pool:
                raise GenerationError("no project LEADS chain left for stale_unresolved")
            pid = self.lead_pool.pop()
            t_b = self.rand_ts(self.project_page_at[pid] + 20 * DAY, TODAY - 5 * DAY)
            old = W.lead_at(pid, t_b)
            owner = W.owner_at(pid, t_b)
            new = self.rng.choice([p for p in W.members_at(owner, t_b) if p != old] or
                                  [p for p in W.members_at(self.other_team(owner), t_b)])
            author = self.rng.choice(W.members_at(owner, t_b))
            d = self.add_chat(self.team_channel(owner), t_b, author,
                              [self.S(f"{self.disp(new)} leads {self.disp(pid)} now.", self.C("LEADS", new, pid))],
                              ["stale_unresolved"])
            self._declare("LEADS", pid, old, new, d["ts"], correct, tags, "stale_unresolved")
            return
        target = self.take_owns()
        Y = W.owner_at(target, START)
        X = self.other_team(Y)
        nm = self.name(target)
        member = self.rng.choice(W.members_at(Y, START))
        if kind == "chat_contradiction":
            t = self.rand_ts(START + 60 * DAY, TODAY - 5 * DAY)
            author = self.rng.choice([p["id"] for p in W.people if p["id"] not in W.anchor_entities])
            d = self.add_chat(self.rng.choice(["general", "eng", self.team_channel(X)]), t, author,
                              [self.S(f"{self.disp(X)} owns {self.disp(target)} now.", self.C("OWNS", X, target))],
                              ["chat_contradiction"])
            at = d["ts"]
        elif kind == "edit_below":
            t_a = self.rand_day(START + 20 * DAY, TODAY - 200 * DAY)
            t_b = self.rand_day_not_reorg(t_a + 20 * DAY, TODAY - 5 * DAY)
            self.add_doc_wiki(slug(nm) + "-handbook", f"{nm} handbook", member, [
                (t_a, [[self.S(f"{self.disp(Y)} owns {self.disp(target)}.", self.C("OWNS", Y, target))],
                       [self.S(f"Release notes for {nm} are posted every Friday.")]]),
                (t_b, [[self.S(f"Since {iso(t_b)}, {self.disp(X)} owns {self.disp(target)}.", self.C("OWNS", X, target, date=t_b))],
                       [self.S(f"Release notes for {nm} are posted every Friday.")]]),
            ], ["edit_below_record", "edited_doc"])
            at = t_b
        elif kind == "equal":
            d0 = W.active("OWNS", o=target, t=START)[0]["from"]
            t_a = self.rand_day(START + 20 * DAY, TODAY - 20 * DAY)
            self.add_doc_wiki(slug(nm) + "-history", f"{nm} history", member, [
                (t_a, [[self.S(f"Since {iso(d0)}, {self.disp(X)} owns {self.disp(target)}.", self.C("OWNS", X, target, date=d0))],
                       [self.S(f"The first version of {nm} shipped as an internal pilot.")]]),
            ], ["equal_date_dispute"])
            at = d0
        elif kind == "su_prose":
            t_a = self.rand_day(START + 20 * DAY, TODAY - 120 * DAY)
            t_b = self.rand_day_not_reorg(t_a + 20 * DAY, TODAY - 5 * DAY)
            self.add_doc_wiki(slug(nm) + "-notes", f"{nm} notes", member, [
                (t_a, [[self.S(f"{self.disp(Y)} owns {self.disp(target)}.", self.C("OWNS", Y, target))],
                       [self.S(f"Capacity planning for {nm} happens each quarter.")]]),
            ], ["stale_unresolved"])
            att = sorted(set(W.members_at(X, t_b)[:2] + W.members_at(Y, t_b)[:2]))
            self.add_doc_meeting(slug(nm) + "-ownership-sync", f"{nm} ownership sync", t_b, att[0], att,
                                 [[self.S(f"{self.disp(X)} owns {self.disp(target)} now.", self.C("OWNS", X, target)),
                                   self.S("Follow-up questions go to the next staff meeting.")]], ["stale_unresolved"])
            at = t_b
        else:
            raise GenerationError(kind)
        self._declare("OWNS", target, Y, X, at, correct, tags, kind)

    def _declare(self, p: str, key: str, frm: str, to: str, at: int, correct: bool, tags: list[str], kind: str) -> None:
        W = self.W
        W.reserved.add((p, "", key))
        W.declared.append({"change_id": f"chg:{slug(tags[0])}:{slug(key)}:{iso(at)}", "predicate": p, "qualifier": "",
                           "key": key, "from": frm, "to": to, "at": at, "true": bool(correct),
                           "expected_outcome": "disputed", "challenger_correct": bool(correct),
                           "stale_docs": [], "tags": list(tags)})

    # decisions
    def gen_decisions(self) -> None:
        W, rng = self.W, self.rng
        n = TARGETS["decisions"] - len(W.decisions)
        techs = list(TECH_POOL)
        rng.shuffle(techs)
        specs: list[dict] = []
        sys_choices = list(self.gen_systems)
        rng.shuffle(sys_choices)

        def chain(length: int, sid: str) -> None:
            t1, t2, t3 = techs.pop(), techs.pop(), techs.pop()
            a_acc = self.rand_day(START + 20 * DAY, START + 150 * DAY)
            prev = {"title": f"Use {t1} for {self.name(sid)}", "st": [["accepted", a_acc]], "aff": [sid], "tech": t1, "rep": None}
            specs.append(prev)
            last_acc = a_acc
            for t_old, t_new in [(t1, t2), (t2, t3)][: length - 1]:
                prop = self.rand_day(last_acc + 60 * DAY, last_acc + 180 * DAY)
                acc = prop + rng.randint(7, 21) * DAY
                prev["st"].append(["superseded", acc])
                cur = {"title": f"Replace {t_old} with {t_new} for {self.name(sid)}",
                       "st": [["proposed", prop], ["accepted", acc]], "aff": [sid], "tech": t_new, "rep": prev}
                specs.append(cur)
                prev, last_acc = cur, acc

        chain(3, sys_choices[0])
        chain(2, sys_choices[1])
        patterns = [["accepted"], ["proposed", "accepted"], ["proposed", "rejected"], ["proposed"], ["accepted"]]
        targets = sys_choices[2:] + self.gen_projects
        for pat in patterns[: n - len(specs)]:
            tech = techs.pop()
            aff = rng.choice(targets)
            t0 = self.rand_day(START + 10 * DAY, TODAY - 40 * DAY)
            st = [[pat[0], t0]]
            if len(pat) > 1:
                st.append([pat[1], t0 + rng.randint(5, 25) * DAY])
            specs.append({"title": f"Adopt {tech} for {self.name(aff)}", "st": st, "aff": [aff], "tech": tech, "rep": None})
        specs.sort(key=lambda s: (s["st"][0][1], s["title"]))
        nums = sorted(rng.sample([k for k in range(1, 41) if k not in (3, 7)], len(specs)))
        for sp, num in zip(specs, nums):
            sp["number"] = f"ADR-{num:03d}"
            sp["id"] = f"decision:adr-{num:03d}"
        for sp in specs:
            aff = sp["aff"][0]
            t0 = sp["st"][0][1]
            owner = W.owner_at(aff, t0)
            lead = W.lead_at(owner, t0) or W.members_at(owner, t0)[0]
            deciders = [lead]
            others = [p for p in W.members_at(owner, t0) if p != lead]
            if others:
                deciders.append(rng.choice(others))
            if rng.random() < 0.5:
                deciders.append(owner)
            an = self.name(aff)
            rationale = rng.sample([
                f"{an} needs predictable latency as traffic grows through the year.",
                f"The current setup for {an} makes on-call debugging slow and manual.",
                f"{sp['tech']} is already operated by other teams, so support costs stay low.",
                f"Incidents on {an} last quarter traced back to the existing approach.",
                f"Moving to {sp['tech']} lets {an} scale without hand-tuned capacity.",
            ], 2)
            W.decisions.append({
                "id": sp["id"], "number": sp["number"], "title": sp["title"], "date": t0,
                "status_timeline": [{"status": s, "at": t} for s, t in sp["st"]],
                "deciders": deciders, "affects": list(sp["aff"]),
                "replaces": [sp["rep"]["id"]] if sp["rep"] else [],
                "rationale_points": rationale,
                "decision_text": f"We will use {sp['tech']} for {an}.",
                "consequences": f"The owning team updates the {an} runbook and the on-call notes.",
            })

    # tickets
    def gen_tickets(self) -> None:
        W, rng = self.W, self.rng
        used: dict[str, set[int]] = defaultdict(set)
        for t in W.tickets:
            pre, num = t["key"].split("-")
            used[pre].add(int(num))
        used["RDS"] |= {31, 42}
        problems = ["timeouts under peak load", "stale cache entries", "noisy alerts at night", "slow cold starts",
                    "missing audit fields", "a retry storm after deploys", "a flaky integration test", "high p99 latency"]
        targets = self.gen_systems + self.gen_projects[:3]
        n = TARGETS["tickets"] - len(W.tickets)
        replace_idx = set(rng.sample(range(n), 3))
        out = []
        for i in range(n):
            about = rng.choice(targets)
            t0 = self.rand_day(to_ms("2025-02-01"), to_ms("2026-09-25"))
            owner = W.owner_at(about, t0)
            pre = "RDS" if rng.random() < 0.15 else W.team_prefix[owner]
            num = rng.randrange(1, 200)
            while num in used[pre]:
                num = rng.randrange(1, 200)
            used[pre].add(num)
            key = f"{pre}-{num}"
            states = [{"state": "open", "at": t0}]
            t = t0
            if rng.random() < 0.7:
                t = min(t + rng.randint(1, 20) * DAY, TODAY - DAY)
                if t > t0:
                    states.append({"state": "in_progress", "at": t})
                    if rng.random() < 0.6:
                        t2 = min(t + rng.randint(2, 30) * DAY, TODAY - DAY)
                        if t2 > t:
                            states.append({"state": "done", "at": t2})
                            t = t2
            assignees = []
            if rng.random() < 0.8:
                at = states[1]["at"] if len(states) > 1 and rng.random() < 0.4 else t0
                pool = W.members_at(W.owner_at(about, at), at)
                who = rng.choice(pool) if rng.random() < 0.85 else W.owner_at(about, at)
                assignees.append({"who": who, "at": at})
                if rng.random() < 0.2 and t - at > 2 * DAY:
                    at2 = self.rand_day(at + DAY, t - DAY)
                    others = [p for p in W.members_at(W.owner_at(about, at2), at2) if p != who]
                    if others:
                        assignees.append({"who": rng.choice(others), "at": at2})
            abouts = [{"about": about, "at": t0}]
            if i in replace_idx:
                t_r = self.rand_day(t0 + DAY, max(t0 + DAY, TODAY - 2 * DAY))
                abouts.append({"about": rng.choice([x for x in self.gen_systems if x != about]), "at": t_r})
                t = max(t, t_r)
            problem = rng.choice(problems)
            creator = rng.choice(W.members_at(owner, t0))
            out.append({"key": key, "id": "ticket:" + key.lower(),
                        "title": f"{self.name(about)}: {problem}",
                        "description": f"{self.disp(about)} shows {problem} since the last release.",
                        "created_by": creator, "about_timeline": abouts, "assignee_timeline": assignees,
                        "state_timeline": states, "comments": [], "distractors": [], "_last": t})
        keys = [x["key"] for x in out]
        comment_tpl = ["Reproduced on staging, logs are attached.", "This overlaps with {k}, linking them.",
                       "Blocked until {k} lands.", "Moved to the next sprint after triage.",
                       "Rolled out the fix behind a feature flag.", "Same symptom as {k}, probably one root cause."]
        for tk in out:
            last = tk.pop("_last")
            for _ in range(rng.choice([0, 0, 1, 1, 2])):
                at = self.rand_day(tk["state_timeline"][0]["at"], last)
                other = rng.choice([k for k in keys if k != tk["key"]])
                tk["comments"].append({"author": rng.choice(W.members_at(W.owner_at(tk["about_timeline"][0]["about"], at), at)
                                                            or [tk["created_by"]]),
                                       "at": at, "sentences": [self.S(rng.choice(comment_tpl).format(k=other))]})
            tk["comments"].sort(key=lambda c: c["at"])
            W.tickets.append(tk)

    # generic prose
    def free(self, p: str, q: str, s: str, o: str) -> bool:
        ch = chain_of(p, q, s, o)
        if ch in self.W.reserved:
            return False
        ids = {s, o} | ({ch[2]} if ":" in ch[2] and ">" not in ch[2] else set())
        return not (ids & self.W.anchor_entities)

    def gen_generic_wiki(self) -> None:
        W, rng = self.W, self.rng
        for sid in self.gen_systems:
            t = self.rand_day(START + 10 * DAY, START + 300 * DAY)
            nm = self.name(sid)
            claims_s = []
            owner = W.owner_at(sid, t)
            if self.free("OWNS", "", owner, sid):
                claims_s.append(self.S(f"{self.disp(owner)} owns {self.disp(sid)}.", self.C("OWNS", owner, sid)))
            proj = W.project_at(sid, t)
            if proj and self.free("PART_OF", "", sid, proj):
                claims_s.append(self.S(f"{self.disp(sid)} is part of {self.disp(proj)}.", self.C("PART_OF", sid, proj)))
            deps = [self.S(f"{self.disp(sid)} depends on {self.disp(o)}.", self.C("DEPENDS_ON", sid, o))
                    for o in W.deps_at(sid, t) if self.free("DEPENDS_ON", "", sid, o)]
            paras = [[self.S(f"{nm} is a tier {self.W.ent(sid)['tier']} service.")] + claims_s]
            if deps:
                paras.append(deps)
            paras.append([self.S(f"Deploys of {nm} go through the standard pipeline with a canary stage.")])
            author = rng.choice(W.members_at(owner, t))
            self.add_doc_wiki(f"service-{slug(nm)}", f"{nm} service page", author, [(t, paras)], [])
        for pid in self.gen_projects:
            t = self.project_page_at[pid]
            nm = self.name(pid)
            owner = W.owner_at(pid, t)
            lead = W.lead_at(pid, t)
            sents = [self.S(f"{nm} is one of this year's planned projects.")]
            if self.free("OWNS", "", owner, pid):
                sents.append(self.S(f"{self.disp(owner)} owns {self.disp(pid)}.", self.C("OWNS", owner, pid)))
            sents.append(self.S(f"{self.disp(lead)} leads {self.disp(pid)}.", self.C("LEADS", lead, pid)))
            self.add_doc_wiki(f"project-{slug(nm)}", f"{nm} project page", lead, [(t, [sents,
                              [self.S("Status updates are shared in the monthly review.")]])], [])
        for tid in self.gen_teams:
            t = self.rand_day(START + 10 * DAY, START + 250 * DAY)
            nm = self.name(tid)
            lead = W.lead_at(tid, t)
            sents = [self.S(f"{nm} runs planning every second Monday.")]
            if self.free("LEADS", "", lead, tid):
                sents.append(self.S(f"{self.disp(lead)} leads {self.disp(tid)}.", self.C("LEADS", lead, tid)))
            self.add_doc_wiki(f"team-{slug(nm)}", f"{nm} team page", lead, [(t, [sents])], [])
        a, b = self.dup_people
        t = self.rand_day(START + 60 * DAY, TODAY - 60 * DAY)
        self.add_doc_wiki("billing-migration", "Billing migration", a, [(t, [
            [self.S("Billing-v2 takes all new merchants, while Billing keeps serving existing contracts until the cutover."),
             self.S(f"{self.name(a)} and {self.name(b)} pair on the reconciliation checks between Billing and Billing-v2.")],
            [self.S("The billing-svc and billing-v2-svc deploy pipelines stay separate until then.")]])], ["near_dup_name"])

    def gen_generic_meetings(self) -> None:
        W, rng = self.W, self.rng
        existing = sum(1 for d in W.docs if d["kind"] == "meeting")
        todo = list(self.works_on)
        rng.shuffle(todo)
        gen_decisions = [d for d in W.decisions if d["id"] not in W.anchor_entities]
        k = 0
        while existing < TARGETS["meetings"] or todo:
            tid = self.gen_teams[k % len(self.gen_teams)]
            k += 1
            date = self.rand_day(START + 30 * DAY, TODAY - 5 * DAY)
            att = W.members_at(tid, date)
            att = rng.sample(att, min(4, len(att)))
            sents = [self.S(f"{self.name(tid)} sync covered roadmap risks and hiring.")]
            for iv in todo[:3]:
                sents.append(self.S(f"{self.disp(iv['s'])} works on {self.disp(iv['o'])}.", self.C("WORKS_ON", iv["s"], iv["o"])))
            todo = todo[3:]
            acc = [d for d in gen_decisions if any(s["status"] == "accepted" and s["at"] <= date for s in d["status_timeline"])
                   and _status_at(d, date) == "accepted"]
            para2 = []
            if acc:
                d = rng.choice(acc)
                para2.append(self.S(f"{d['number']} was accepted.", self.C("HAS_STATUS", d["id"], v="accepted")))
            open_t = [t for t in W.tickets if t["state_timeline"][0]["at"] <= date and t["id"] not in W.anchor_entities]
            if open_t:
                para2.append(self.S(f"Follow-ups are tracked in {rng.choice(open_t)['key']}."))
            paras = [sents] + ([para2] if para2 else [])
            self.add_doc_meeting(f"{slug(self.name(tid))}-sync-{iso(date)}", f"{self.name(tid)} sync {iso(date)}", date,
                                 att[0], sorted(att), paras, [])
            existing += 1

    # chat
    def gen_chat(self) -> None:
        W, rng = self.W, self.rng
        lo, hi = START + 7 * DAY, TODAY - DAY
        gen_people = [p["id"] for p in W.people if p["id"] not in W.anchor_entities]
        channels = ["general", "eng", "incidents"] + [self.team_channel(t) for t in self.gen_teams]

        def author_for(channel: str, t: int) -> str:
            for tid in self.gen_teams:
                if self.team_channel(tid) == channel:
                    mem = W.members_at(tid, t)
                    if mem:
                        return rng.choice(mem)
            return rng.choice(gen_people)

        def n_chat() -> int:
            return sum(1 for d in W.docs if d["kind"] == "chat")

        # hedges (mention only)
        for _ in range(6):
            t = self.rand_ts(lo, hi)
            ch = rng.choice(channels)
            form = rng.randrange(3)
            if form == 0:
                text = f"I think {self.disp(rng.choice(self.gen_teams))} owns {self.disp(rng.choice(self.gen_systems))}?"
            elif form == 1:
                text = f"Maybe {self.disp(rng.choice(gen_people))} leads {self.disp(rng.choice(self.gen_teams))}?"
            else:
                a, b = rng.sample(self.gen_systems, 2)
                text = f"I think {self.disp(a)} depends on {self.disp(b)}, maybe?"
            self.add_chat(ch, t, author_for(ch, t), [{"text": text, "claims": [], "hedge": True}], ["hedge"])
        # restatement traps: a question repeated verbatim, unanswered
        for _ in range(3):
            t = self.rand_ts(lo, hi - DAY)
            ch = rng.choice(channels)
            form = rng.randrange(3)
            if form == 0:
                q = f"Who owns {self.name(rng.choice(self.gen_systems))}?"
            elif form == 1:
                q = f"Who leads {self.name(rng.choice(self.gen_teams))}?"
            else:
                q = f"Which project is {self.name(rng.choice(self.gen_systems))} part of?"
            a1 = author_for(ch, t)
            root = self.add_chat(ch, t, a1, [self.S(q)], [])
            a2 = rng.choice([p for p in gen_people if p != a1])
            self.add_chat(ch, t + rng.randint(5, 90) * 60_000, a2, [self.S(q)], ["restatement_trap"], thread_ts=root["ts"])
        # near-duplicate names
        a, b = self.dup_people
        nd = ["Billing-v2 is taking the new merchants, Billing stays on the old flow for now.",
              "Is the Billing-v2 cutover blocking the Billing reconciliation job?",
              f"{self.name(a)} and {self.name(b)} are both out on Friday.",
              f"Thanks {self.W.ent(a)['aliases'][0]}, merged the billing-v2-svc fix.",
              f"Thanks {self.W.ent(b)['aliases'][0]}, the billing-svc alert is quiet again.",
              "Reminder that Billing and Billing-v2 have separate on-call rotas."]
        for text in nd:
            t = self.rand_ts(lo, hi)
            ch = rng.choice(channels)
            self.add_chat(ch, t, author_for(ch, t), [self.S(text)], ["near_dup_name"])
        # restatements of current facts (rank 1), only on free chains
        cands = [iv for iv in W.timeline if iv["p"] in ("OWNS", "LEADS", "DEPENDS_ON", "PART_OF", "WORKS_ON")
                 and self.free(iv["p"], iv["q"], iv["s"], iv["o"])]
        cands.sort(key=lambda iv: (iv["p"], iv["s"], iv["o"], iv["from"]))
        made = 0
        while made < 40:
            iv = rng.choice(cands)
            a_lo = max(iv["from"] + DAY, lo)
            a_hi = min(iv["to"] - 2 * DAY, hi)
            if a_hi <= a_lo:
                continue
            t = self.rand_ts(a_lo, a_hi)
            s, o = self.disp(iv["s"]), self.disp(iv["o"])
            text = {"OWNS": rng.choice([f"{s} owns {o}.", f"For context, {s} owns {o}."]),
                    "LEADS": f"{s} leads {o}.", "DEPENDS_ON": f"{s} depends on {o}.",
                    "PART_OF": f"{s} is part of {o}.", "WORKS_ON": f"{s} works on {o}."}[iv["p"]]
            ch = rng.choice(channels)
            self.add_chat(ch, t, author_for(ch, t), [self.S(text, self.C(iv["p"], iv["s"], iv["o"], q=iv["q"]))], [])
            made += 1
        # hyphen ids and filler
        gen_tickets = [t for t in W.tickets if t["id"] not in W.anchor_entities]
        hyphen_tpl = ["Picking up {k} today.", "{k} is blocked on a config change.", "Closed {k}, the fix is live.",
                      "Can someone triage {k}?", "Linked {k} to {k2}, same root cause."]
        filler_tpl = ["Deploying {sys} to staging after lunch.", "Can someone review the {sys} runbook changes?",
                      "The {team} demo moved to Thursday.", "The {proj} retro notes are up.",
                      "Who has context on the {sys} alerts from last night?",
                      "Load test for {sys} finished, numbers look normal.",
                      "Reminder that {team} planning starts at ten.", "Pairing with {person} on {sys} today.",
                      "{sys} dashboards are back after the metrics outage.",
                      "Kicking off the {proj} design review next week."]
        target = TARGETS["chat"]
        n_hyphen = 50
        while n_chat() < target:
            t = self.rand_ts(lo, hi)
            ch = rng.choice(channels)
            if n_hyphen > 0:
                n_hyphen -= 1
                tk = [x for x in gen_tickets if x["state_timeline"][0]["at"] <= t] or gen_tickets
                k1 = rng.choice(tk)["key"]
                k2 = rng.choice(gen_tickets)["key"]
                text = rng.choice(hyphen_tpl).format(k=k1, k2=k2)
            else:
                text = rng.choice(filler_tpl).format(sys=self.disp(rng.choice(self.gen_systems)),
                                                     team=self.name(rng.choice(self.gen_teams)),
                                                     proj=self.name(rng.choice(self.gen_projects)),
                                                     person=self.disp(rng.choice(gen_people)))
            thread_ts = None
            if rng.random() < 0.15:
                roots = [d for d in W.docs if d["kind"] == "chat" and d["channel"] == ch and d["thread_ts"] is None
                         and not d.get("thread") and t - 2 * DAY < d["ts"] < t]
                if roots:
                    thread_ts = rng.choice(roots)["ts"]
            self.add_chat(ch, t, author_for(ch, t), [self.S(text)], [], thread_ts=thread_ts)

    def resolve_threads(self) -> None:
        roots: dict[tuple, int] = {}
        for d in self.W.docs:
            if d["kind"] == "chat" and d.get("thread"):
                k = (d["channel"], d["thread"])
                roots[k] = min(roots.get(k, MAX), d["ts"])
        for d in self.W.docs:
            if d["kind"] == "chat" and d.get("thread"):
                r = roots[(d["channel"], d["thread"])]
                d["thread_ts"] = None if d["ts"] == r else r


def _status_at(d: dict, t: int) -> str | None:
    cur = None
    for s in d["status_timeline"]:
        if s["at"] <= t:
            cur = s["status"]
    return cur


# changes and facts

def change_id_for(p: str, q: str, key: str, at: int) -> str:
    return f"chg:{slug(p + ('-' + q if q else ''))}:{slug(key)}:{iso(at)}"


def derive_changes(W: World) -> list[dict]:
    """Every change of every chain in the gold timeline, merged with the authored declarations."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for iv in W.all_intervals():
        groups[iv_chain(iv)].append(iv)
    auto: list[dict] = []
    for ch in sorted(groups):
        p, q, key = ch
        lst = sorted(groups[ch], key=lambda iv: iv["from"])
        if is_functional(p, q):
            for a, b in zip(lst, lst[1:]):
                if a["to"] != b["from"]:
                    raise GenerationError(f"chain {ch} has a hole or overlap between {iso(a['from'])} and {iso(b['from'])}")
                auto.append((ch, iv_value(a), iv_value(b), b["from"], lst[0]["src"]))
            if lst[-1]["to"] < MAX:
                auto.append((ch, iv_value(lst[-1]), "", lst[-1]["to"], lst[0]["src"]))
        else:
            if len(lst) != 1:
                raise GenerationError(f"non-functional chain {ch} reopens")
            if lst[0]["to"] < MAX:
                auto.append((ch, "+", "-", lst[0]["to"], lst[0]["src"]))
    declared = {(c["predicate"], c["qualifier"], c["key"], c["at"], c["from"], c["to"]): c for c in W.declared}
    used = set()
    out = []
    for (p, q, key), frm, to, at, src in auto:
        k = (p, q, key, at, frm, to)
        if k in declared:
            c = dict(declared[k])
            used.add(k)
        else:
            tags = list(W.change_tags.get((p, q, key, at), []))
            if at == W.D_reorg and src == "record":
                tags.append("reorg")
            c = {"change_id": change_id_for(p, q, key, at), "predicate": p, "qualifier": q, "key": key,
                 "from": frm, "to": to, "at": at, "true": True, "expected_outcome": "resolved",
                 "challenger_correct": None, "stale_docs": None, "tags": tags}
        ents = {x for x in (key, frm, to) if ":" in x}
        for x in list(ents):
            if ">" in x:
                ents |= set(x.split(">"))
        if ents & W.anchor_entities and "anchor" not in c["tags"]:
            c["tags"] = ["anchor"] + c["tags"]
        out.append(c)
    for k, c in declared.items():
        if k in used:
            continue
        if c["expected_outcome"] == "resolved":
            raise GenerationError(f"declared resolved change {c['change_id']} is not in the gold timeline")
        out.append(dict(c))
    out.sort(key=lambda c: (c["at"], c["predicate"], c["key"], c["change_id"]))
    ids = [c["change_id"] for c in out]
    if len(ids) != len(set(ids)):
        raise GenerationError("duplicate change ids")
    return out


def _with_value(p: str, q: str, key: str, value: str) -> tuple[str, str, str]:
    side = registry.get(p, q).key_side
    if side == "object":
        return value, key, ""
    if ":" in value:
        return key, value, ""
    return key, "", value


def build_facts(W: World, changes: list[dict]) -> list[dict]:
    """The true timeline: gold intervals, adjusted where a disputed challenger was right."""
    ivs = W.all_intervals()
    for c in changes:
        if c["expected_outcome"] != "disputed" or not c["true"]:
            continue
        p, q, key, at = c["predicate"], c["qualifier"], c["key"], c["at"]
        hits = [iv for iv in ivs if iv_chain(iv) == (p, q, key) and iv["from"] <= at < iv["to"]]
        if len(hits) != 1 or iv_value(hits[0]) != c["from"]:
            raise GenerationError(f"cannot apply true challenger {c['change_id']}")
        iv = hits[0]
        end = iv["to"]
        iv["to"] = at
        s, o, v = _with_value(p, q, key, c["to"])
        ivs.append({"p": p, "q": q, "s": s, "o": o, "v": v, "from": at, "to": end, "src": "truth"})
        if iv["from"] == at:
            ivs.remove(iv)
    facts = []
    for iv in ivs:
        facts.append({"predicate": iv["p"], "qualifier": iv["q"], "subject": iv["s"], "object": iv["o"],
                      "value": iv["v"], "valid_from": iv["from"], "valid_to": iv["to"], "negated": False})
        if not is_functional(iv["p"], iv["q"]) and iv["to"] < MAX:
            facts.append({"predicate": iv["p"], "qualifier": iv["q"], "subject": iv["s"], "object": iv["o"],
                          "value": iv["v"], "valid_from": iv["to"], "valid_to": MAX, "negated": True})
    facts.sort(key=lambda f: (f["predicate"], f["qualifier"], f["subject"], f["object"], f["value"],
                              f["valid_from"], f["negated"]))
    for i, f in enumerate(facts, 1):
        f["fact_id"] = f"f{i:04d}"
    return [{"fact_id": f["fact_id"], **{k: f[k] for k in ("predicate", "qualifier", "subject", "object", "value",
                                                            "valid_from", "valid_to", "negated")}} for f in facts]


# after rendering

def attach_liveness(revs: list[dict]) -> None:
    """A claim is live unless a later revision of its doc drops it without stating another
    value in the same chain (05 §2 step 9: removed vs replaced)."""
    by_doc: dict[str, list[dict]] = defaultdict(list)
    for r in revs:
        by_doc[r["doc_key"]].append(r)
    for lst in by_doc.values():
        lst.sort(key=lambda r: r["updated_at"])
        idents = [{_ident(c) for c in r["claims"]} for r in lst]
        for i, r in enumerate(lst):
            for c in r["claims"]:
                c["live"] = True
                for j in range(i + 1, len(lst)):
                    if _ident(c) in idents[j]:
                        continue
                    ch, val = claim_chain(c), claim_value(c)
                    c["live"] = any(claim_chain(d) == ch and claim_value(d) != val for d in lst[j]["claims"])
                    break


def _ident(c: dict) -> tuple:
    return (c["p"], c["q"], c["s"], c["o"], c["v"], c["neg"], c["stated_at"])


def attach_refs(revs: list[dict], facts: list[dict], changes: list[dict]) -> None:
    fidx: dict[tuple, list[dict]] = defaultdict(list)
    for f in facts:
        fidx[(f["predicate"], f["qualifier"], f["subject"], f["object"], f["value"], f["negated"])].append(f)
    cidx: dict[tuple, list[dict]] = defaultdict(list)
    for c in changes:
        cidx[(c["predicate"], c["qualifier"], c["key"])].append(c)
    for r in revs:
        for c in r["claims"]:
            refs = []
            for f in fidx[(c["p"], c["q"], c["s"], c["o"], c["v"], c["neg"])]:
                if f["valid_from"] <= c["stated_at"] < f["valid_to"]:
                    refs.append(("fact:" + f["fact_id"], "fact"))
            val = claim_value(c)
            for ch in cidx[claim_chain(c)]:
                if val == ch["from"]:
                    refs.append(("change:" + ch["change_id"], "from"))
                elif val == ch["to"]:
                    refs.append(("change:" + ch["change_id"], "to"))
            if not refs:
                raise GenerationError(f"sentence {c['text']!r} in {r['doc_key']} states nothing in the world model")
            c["refs"] = refs


def attach_statements(revs: list[dict], changes: list[dict]) -> None:
    by_chain: dict[tuple, list[tuple[dict, dict]]] = defaultdict(list)
    for r in revs:
        for c in r["claims"]:
            by_chain[claim_chain(c)].append((r, c))
    for ch in changes:
        sts = []
        for r, c in by_chain[(ch["predicate"], ch["qualifier"], ch["key"])]:
            val = claim_value(c)
            states = "from" if val == ch["from"] else "to" if val == ch["to"] else None
            if states:
                sts.append({"doc_key": r["doc_key"], "updated_at": r["updated_at"], "form": c["form"], "rank": c["rank"],
                            "stated_at": c["stated_at"], "states": states, "live": c["live"]})
        sts.sort(key=lambda s: (s["stated_at"], s["doc_key"], s["updated_at"], s["states"]))
        ch["statements"] = sts


def declare_stale_docs(revs: list[dict], changes: list[dict]) -> None:
    """For resolved changes without an authored list: every doc whose latest revision still
    states the replaced value and not the new one (05 §3.1 stale-docs)."""
    latest: dict[str, dict] = {}
    for r in revs:
        if r["doc_key"] not in latest or r["updated_at"] > latest[r["doc_key"]]["updated_at"]:
            latest[r["doc_key"]] = r
    for ch in changes:
        if ch["stale_docs"] is not None:
            continue
        if ch["expected_outcome"] != "resolved":
            ch["stale_docs"] = []
            continue
        chain = (ch["predicate"], ch["qualifier"], ch["key"])
        stale = []
        for dk, r in latest.items():
            vals = {claim_value(c) for c in r["claims"] if claim_chain(c) == chain}
            if ch["from"] in vals and ch["to"] not in vals:
                stale.append(dk)
        ch["stale_docs"] = sorted(stale)


# entry point

def generate(seed: int, anchor: dict | None = None) -> World:
    return Generator(seed, anchor).run()


def build_seed(seed: int, anchor: dict | None = None, mutate=None, paraphrase: bool = False):
    """Generate, render and check one seed. Returns (world_yaml_dict, files, manifest).

    `mutate(world_dict_changes)` is a test hook applied to the declarations before the checks."""
    from world import checks, render

    W = generate(seed, anchor)
    changes = derive_changes(W)
    facts = build_facts(W, changes)
    files, revs = render.render_world(W, paraphrase=paraphrase)
    attach_liveness(revs)
    attach_refs(revs, facts, changes)
    attach_statements(revs, changes)
    declare_stale_docs(revs, changes)
    manifest = render.build_manifest(W, revs)
    if mutate is not None:
        mutate(changes)
    world = to_world_yaml(W, facts, changes, revs)
    checks.run_all(W, world, manifest, revs, files)
    return world, files, manifest


def to_world_yaml(W: World, facts: list[dict], changes: list[dict], revs: list[dict]) -> dict:
    renders: dict[str, dict] = {}
    for r in sorted(revs, key=lambda r: (r["doc_key"], r["updated_at"])):
        e = renders.setdefault(r["doc_key"], {"doc_key": r["doc_key"], "kind": r["kind"], "revisions": [],
                                              "distractors": r["distractors"]})
        e["revisions"].append(r["updated_at"])
    distractors = []
    for c in changes:
        for t in c["tags"]:
            if t not in ("anchor", "reorg", "balance_compensation"):
                distractors.append({"type": t, "change_id": c["change_id"]})
    for e in renders.values():
        for t in e["distractors"]:
            distractors.append({"type": t, "doc_key": e["doc_key"]})
    for pair in W.near_dup_pairs:
        distractors.append({"type": "near_dup_name", "entities": list(pair)})
    return {
        "seed": W.seed,
        "company": dict(W.company),
        "D_transfer": W.D_transfer,
        "D_reorg": W.D_reorg,
        "demo_identity": W.demo_identity,
        "anchor": dict(W.anchor_ids),
        "people": [{"id": p["id"], "name": p["name"], "aliases": list(p["aliases"]), "title": p["title"]} for p in W.people],
        "teams": [{"id": t["id"], "name": t["name"], "aliases": list(t["aliases"])} for t in W.teams],
        "projects": [{"id": p["id"], "name": p["name"], "aliases": list(p["aliases"])} for p in W.projects],
        "systems": [{"id": s["id"], "name": s["name"], "aliases": list(s["aliases"]), "tier": s["tier"]} for s in W.systems],
        "facts": facts,
        "changes": [{k: c[k] for k in ("change_id", "predicate", "qualifier", "key", "from", "to", "at", "true",
                                       "statements", "expected_outcome", "challenger_correct", "stale_docs", "tags")}
                    for c in changes],
        "decisions": [{k: d[k] for k in ("id", "number", "title", "date", "status_timeline", "deciders", "affects",
                                         "replaces", "rationale_points")} for d in W.decisions],
        "tickets": [{"key": t["key"], "id": t["id"], "title": t["title"], "about_timeline": t["about_timeline"],
                     "assignee_timeline": t["assignee_timeline"], "state_timeline": t["state_timeline"]} for t in W.tickets],
        "near_dup_pairs": [list(p) for p in W.near_dup_pairs],
        "distractors": distractors,
        "renders": list(renders.values()),
    }
