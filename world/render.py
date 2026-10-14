"""Renderer: writes every document per `docs/render-contract.md` and records, for each
sentence that states something, its exact character range (05 §3.2).

Offsets are into the rendered **file content**, except chat, where they are into the
message's `text` field. Ticket JSON strings never contain characters JSON escapes, so
offsets into the file equal offsets into the decoded strings.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict

from brain.ids import doc_key as mk_doc_key
from world import paraphrase as para
from world.common import MAX, GenerationError, iso, word_re

KIND_DIR = {"roster": "roster", "catalog": "catalog", "adr": "adr", "ticket": "tickets",
            "wiki": "wiki", "meeting": "meetings", "chat": "chat"}
PHASE = {"roster": 1, "catalog": 1, "adr": 1, "ticket": 1, "wiki": 2, "meeting": 2, "chat": 2}
KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")


class Buf:
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.n = 0

    def add(self, s: str) -> tuple[int, int]:
        start = self.n
        self.parts.append(s)
        self.n += len(s)
        return start, self.n

    def text(self) -> str:
        return "".join(self.parts)


def _claim(c: dict, stated_at: int, form: str, rank: int, span: tuple[int, int], text: str) -> dict:
    return {"p": c["p"], "q": c.get("q", ""), "s": c["s"], "o": c.get("o", ""), "v": c.get("v", ""),
            "neg": bool(c.get("neg", False)), "stated_at": stated_at, "form": form, "rank": rank,
            "char_start": span[0], "char_end": span[1], "text": text}


def _sc(p, s, o="", v="", q="", neg=False):
    return {"p": p, "q": q, "s": s, "o": o, "v": v, "neg": neg}


def _rev(kind: str, doc_key: str, system: str, external_id: str, path: str, title: str, uri: str,
         updated_at: int, author: str | None, distractors: list[str]) -> dict:
    return {"doc_key": doc_key, "kind": kind, "path": path, "system": system, "external_id": external_id,
            "title": title, "uri": uri, "created_at": updated_at, "updated_at": updated_at, "author_id": author,
            "phase": PHASE[kind], "distractors": list(distractors), "claims": [], "extras": [], "hedges": [],
            "content": "", "prose": ""}


def _intervals(W, preds) -> list[dict]:
    return [iv for iv in W.timeline if iv["src"] == "record" and iv["p"] in preds
            and (iv["p"] != "LEADS" or iv["o"].startswith("team:"))]


def _revision_dates(W, ivs) -> list[int]:
    start, today = W.company["start_date"], W.company["today"]
    ds = {start}
    for iv in ivs:
        for x in (iv["from"], iv["to"]):
            if start < x <= today and x != MAX:
                ds.add(x)
    return sorted(ds)


def _active(ivs, t):
    return [iv for iv in ivs if iv["from"] <= t < iv["to"]]


# roster

def render_roster(W, t: int) -> dict:
    ivs = _intervals(W, ("MEMBER_OF", "LEADS"))
    act = _active(ivs, t)
    ext = "org"
    r = _rev("roster", mk_doc_key("roster", "hr", ext), "hr", ext, f"roster/org@{t}.md", "Organisation roster",
             "https://hr.example/org", t, None, [])
    b = Buf()
    b.add("# Organisation roster\n\n")
    for team in sorted(W.teams, key=lambda x: x["name"]):
        tid = team["id"]
        leads = [iv for iv in act if iv["p"] == "LEADS" and iv["o"] == tid]
        if len(leads) > 1:
            raise GenerationError(f"roster {iso(t)}: {tid} has two leads")
        lead = leads[0] if leads else None
        rows = [iv for iv in act if iv["p"] == "MEMBER_OF" and iv["o"] == tid]
        rows.sort(key=lambda iv: (not (lead and iv["s"] == lead["s"] and iv["q"] == "primary"), W.ent(iv["s"])["name"]))
        b.add(f"## Team: {team['name']} ({tid})\n\n| Person | ID | Role | Primary | From |\n|---|---|---|---|---|\n")
        lead_rendered = False
        for m in rows:
            is_lead = bool(lead and m["s"] == lead["s"] and m["q"] == "primary")
            if is_lead and lead["from"] != m["from"]:
                raise GenerationError(f"roster {iso(t)}: lead row of {m['s']} cannot carry two From dates")
            line = (f"| {W.ent(m['s'])['name']} | {m['s']} | {'lead' if is_lead else 'member'} | "
                    f"{'yes' if m['q'] == 'primary' else 'no'} | {iso(m['from'])} |")
            span = b.add(line)
            b.add("\n")
            r["claims"].append(_claim(_sc("MEMBER_OF", m["s"], tid, q=m["q"]), m["from"], "structured", 4, span, line))
            if is_lead:
                lead_rendered = True
                r["claims"].append(_claim(_sc("LEADS", m["s"], tid), lead["from"], "structured", 4, span, line))
        if lead and not lead_rendered:
            raise GenerationError(f"roster {iso(t)}: lead {lead['s']} of {tid} is not a primary member")
        b.add("\n")
    b.add("## Teams\n\n| ID | Name | Aliases |\n|---|---|---|\n")
    for team in sorted(W.teams, key=lambda x: x["id"]):
        b.add(f"| {team['id']} | {team['name']} | {'; '.join(team['aliases'])} |\n")
    b.add("\n## People\n\n| ID | Name | Aliases | Title |\n|---|---|---|---|\n")
    for p in sorted(W.people, key=lambda x: x["id"]):
        b.add(f"| {p['id']} | {p['name']} | {'; '.join(p['aliases'])} | {p['title']} |\n")
    r["content"] = b.text()
    return r


# catalogue

def _q(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def render_catalog(W, t: int) -> dict:
    ivs = _intervals(W, ("OWNS", "PART_OF", "DEPENDS_ON"))
    act = _active(ivs, t)
    ext = "services"
    r = _rev("catalog", mk_doc_key("catalog", "backstage", ext), "backstage", ext, f"catalog/services@{t}.yaml",
             "Service catalogue", "https://backstage.example/catalog/services", t, None, [])
    b = Buf()

    def owner_of(eid):
        o = [iv for iv in act if iv["p"] == "OWNS" and iv["o"] == eid]
        if len(o) != 1:
            raise GenerationError(f"catalogue {iso(t)}: {eid} has {len(o)} owners")
        return o[0]

    b.add("projects:\n")
    for p in sorted(W.projects, key=lambda x: x["id"]):
        own = owner_of(p["id"])
        lines = [f"  - id: {p['id']}", f"    name: {_q(p['name'])}", f"    aliases: {json.dumps(p['aliases'], ensure_ascii=False)}",
                 f"    owner: {own['s']}", f"    owner_from: {iso(own['from'])}"]
        text = "\n".join(lines)
        span = b.add(text)
        b.add("\n")
        r["claims"].append(_claim(_sc("OWNS", own["s"], p["id"]), own["from"], "structured", 4, span, text))
    b.add("systems:\n")
    for s in sorted(W.systems, key=lambda x: x["id"]):
        sid = s["id"]
        own = owner_of(sid)
        part = [iv for iv in act if iv["p"] == "PART_OF" and iv["s"] == sid]
        deps = sorted((iv for iv in act if iv["p"] == "DEPENDS_ON" and iv["s"] == sid), key=lambda iv: iv["o"])
        dropped = sorted((iv for iv in ivs if iv["p"] == "DEPENDS_ON" and iv["s"] == sid and iv["to"] <= t),
                         key=lambda iv: iv["o"])
        lines = [f"  - id: {sid}", f"    name: {_q(s['name'])}", f"    aliases: {json.dumps(s['aliases'], ensure_ascii=False)}",
                 f"    tier: {s['tier']}", f"    owner: {own['s']}", f"    owner_from: {iso(own['from'])}"]
        if part:
            lines += [f"    project: {part[0]['o']}", f"    project_from: {iso(part[0]['from'])}"]
        if deps:
            lines.append("    depends_on:")
            lines += [f"      - {{id: {d['o']}, from: {iso(d['from'])}}}" for d in deps]
        else:
            lines.append("    depends_on: []")
        if dropped:
            lines.append("    dropped_depends_on:")
            lines += [f"      - {{id: {d['o']}, at: {iso(d['to'])}}}" for d in dropped]
        text = "\n".join(lines)
        span = b.add(text)
        b.add("\n")
        r["claims"].append(_claim(_sc("OWNS", own["s"], sid), own["from"], "structured", 4, span, text))
        if part:
            r["claims"].append(_claim(_sc("PART_OF", sid, part[0]["o"]), part[0]["from"], "structured", 4, span, text))
        for d in deps:
            r["claims"].append(_claim(_sc("DEPENDS_ON", sid, d["o"]), d["from"], "structured", 4, span, text))
        for d in dropped:
            r["claims"].append(_claim(_sc("DEPENDS_ON", sid, d["o"], neg=True), d["to"], "structured", 4, span, text))
    r["content"] = b.text()
    return r


# ADR

def render_adr(W, d: dict) -> list[dict]:
    out = []
    num_of = {x["id"]: x["number"] for x in W.decisions}
    st = d["status_timeline"]
    first_person = next((x for x in d["deciders"] if x.startswith("person:")), None)
    for i, s in enumerate(st):
        status, updated = s["status"], s["at"]
        date = updated
        if status == "superseded":
            date = next(x["at"] for x in reversed(st[:i]) if x["status"] != "superseded")
        status_from = updated if status == "superseded" else date
        r = _rev("adr", mk_doc_key("adr", "repo", d["number"]), "repo", d["number"], f"adr/{d['number']}@{updated}.md",
                 f"{d['number']}: {d['title']}", f"https://git.example/adr/{d['number']}.md", updated, first_person, [])
        r["created_at"] = st[0]["at"]
        b = Buf()
        fm = ["---", f"number: {d['number']}", f"title: {_q(d['title'])}", f"status: {status}", f"date: {iso(date)}",
              f"deciders: [{', '.join(d['deciders'])}]", f"affects: [{', '.join(d['affects'])}]",
              f"replaces: [{', '.join(num_of[x] for x in d['replaces'])}]", "---"]
        fm_text = "\n".join(fm)
        span = b.add(fm_text)
        b.add("\n")
        r["claims"].append(_claim(_sc("HAS_STATUS", d["id"], v=status), status_from, "structured", 4, span, fm_text))
        for x in d["deciders"]:
            r["claims"].append(_claim(_sc("DECIDED_BY", d["id"], x), date, "structured", 4, span, fm_text))
        for x in d["affects"]:
            r["claims"].append(_claim(_sc("AFFECTS", d["id"], x), date, "structured", 4, span, fm_text))
        for x in d["replaces"]:
            r["claims"].append(_claim(_sc("REPLACES", d["id"], x), date, "structured", 4, span, fm_text))
        body_start = b.n
        b.add("## Context\n\n")
        for rp in d["rationale_points"]:
            sp = b.add(rp)
            b.add("\n\n")
            r["extras"].append({"ref": d["id"], "states": "rationale", "section": "Context",
                                "char_start": sp[0], "char_end": sp[1], "text": rp})
        b.add("## Decision\n\n")
        sp = b.add(d["decision_text"])
        r["extras"].append({"ref": d["id"], "states": "rationale", "section": "Decision",
                            "char_start": sp[0], "char_end": sp[1], "text": d["decision_text"]})
        b.add("\n\n## Consequences\n\n")
        b.add(d["consequences"])
        b.add("\n")
        r["content"] = b.text()
        r["prose"] = r["content"][body_start:]
        out.append(r)
    return out


# ticket

def _jstr(s: str) -> str:
    enc = json.dumps(s, ensure_ascii=False)
    if enc != '"' + s + '"':
        raise GenerationError(f"ticket text needs JSON escaping: {s!r}")
    return enc


def render_ticket(W, t: dict) -> dict:
    events = ([e["at"] for e in t["about_timeline"]] + [e["at"] for e in t["assignee_timeline"]]
              + [e["at"] for e in t["state_timeline"]] + [c["at"] for c in t["comments"]])
    updated = max(events)
    r = _rev("ticket", mk_doc_key("ticket", "jira", t["key"]), "jira", t["key"], f"tickets/{t['key']}@{updated}.json",
             f"{t['key']}: {t['title']}", f"https://jira.example/browse/{t['key']}", updated, t.get("created_by"),
             t.get("distractors", []))
    r["created_at"] = t["state_timeline"][0]["at"]
    b = Buf()
    prose = [t["title"], t["description"]]
    b.add("{\n")
    b.add(f'  "key": {_jstr(t["key"])},\n  "title": {_jstr(t["title"])},\n  "description": {_jstr(t["description"])},\n')

    def rows(name, items, fmt, claims_for):
        if not items:
            b.add(f'  "{name}": [],\n')
            return
        b.add(f'  "{name}": [\n')
        for i, e in enumerate(items):
            text = fmt(e)
            b.add("    ")
            span = b.add(text)
            b.add(",\n" if i + 1 < len(items) else "\n")
            for c in claims_for(i, e):
                r["claims"].append(_claim(c, e["at"], "structured", 4, span, text))
        b.add("  ],\n")

    rows("assignee_history", t["assignee_timeline"], lambda e: f'{{"who": {_jstr(e["who"])}, "at": "{iso(e["at"])}"}}',
         lambda i, e: [_sc("ASSIGNED_TO", t["id"], e["who"])])
    rows("state_history", t["state_timeline"], lambda e: f'{{"state": {_jstr(e["state"])}, "at": "{iso(e["at"])}"}}',
         lambda i, e: [_sc("HAS_STATE", t["id"], v=e["state"])])
    ab = t["about_timeline"]
    rows("component_history", ab, lambda e: f'{{"about": {_jstr(e["about"])}, "at": "{iso(e["at"])}"}}',
         lambda i, e: [_sc("ABOUT", t["id"], e["about"])] + ([_sc("ABOUT", t["id"], ab[i - 1]["about"], neg=True)] if i else []))
    if not t["comments"]:
        b.add('  "comments": []\n')
    else:
        b.add('  "comments": [\n')
        for i, c in enumerate(t["comments"]):
            b.add(f'    {{"author": {_jstr(c["author"])}, "at": "{iso(c["at"])}", "text": "')
            for j, s in enumerate(c["sentences"]):
                if j:
                    b.add(" ")
                _jstr(s["text"])
                span = b.add(s["text"])
                prose.append(s["text"])
                for cl in s["claims"]:
                    r["claims"].append(_claim(cl, cl["date"] if cl.get("date") is not None else c["at"],
                                              "prose", 2, span, s["text"]))
            b.add('"}' + (",\n" if i + 1 < len(t["comments"]) else "\n"))
        b.add("  ]\n")
    b.add("}\n")
    r["content"] = b.text()
    r["prose"] = "\n".join(prose)
    json.loads(r["content"])
    return r


# prose

def _names_in(W, text: str) -> list[str]:
    out = []
    for e in W.entities():
        for n in [e["name"]] + e["aliases"]:
            if word_re(n).search(text) and n in text:
                out.append(n)
    return sorted(set(out))


def _sentence_text(W, s: dict, seed: int, paraphrase: bool) -> str:
    if s["hedge"] or not paraphrase:
        return s["text"]
    return para.paraphrase(s["text"], _names_in(W, s["text"]) + KEY_RE.findall(s["text"]), seed, requested=True)


def _write_sentences(W, b: Buf, r: dict, sentences: list[dict], default_at: int, form: str, rank: int,
                     paraphrase: bool) -> None:
    for j, s in enumerate(sentences):
        if j:
            b.add(" ")
        text = _sentence_text(W, s, W.seed, paraphrase)
        span = b.add(text)
        if s["hedge"]:
            r["hedges"].append(text)
        for c in s["claims"]:
            if c.get("date") is not None and iso(c["date"]) not in text:
                raise GenerationError(f"stated date missing from sentence {text!r}")
            r["claims"].append(_claim(c, c["date"] if c.get("date") is not None else default_at, form, rank, span, text))


def render_prose_doc(W, d: dict, paraphrase: bool) -> list[dict]:
    out = []
    created = min(rv["updated_at"] for rv in d["revisions"])
    for rv in d["revisions"]:
        t = rv["updated_at"]
        if d["kind"] == "wiki":
            r = _rev("wiki", d["doc_key"], "confluence", d["external_id"], f"wiki/{d['external_id']}@{t}.md", d["title"],
                     f"https://wiki.example/{d['external_id']}", t, d["author"], d["distractors"])
        else:
            r = _rev("meeting", d["doc_key"], "notes", d["external_id"], f"meetings/{d['external_id']}@{t}.md", d["title"],
                     f"https://notes.example/{d['external_id']}", t, d["author"], d["distractors"])
        r["created_at"] = created
        b = Buf()
        b.add(f"# {d['title']}\n\n")
        if d["kind"] == "meeting":
            b.add(f"Date: {iso(t)}\nAttendees: {', '.join(d['attendees'])}\n\n")
        body_start = b.n
        for k, paragraph in enumerate(rv["paragraphs"]):
            if k:
                b.add("\n\n")
            _write_sentences(W, b, r, paragraph, t, "prose", 2, paraphrase)
        b.add("\n")
        r["content"] = b.text()
        r["prose"] = r["content"][body_start:]
        out.append(r)
    return out


def render_chat(W, docs: list[dict], paraphrase: bool) -> tuple[dict[str, str], list[dict]]:
    files: dict[str, str] = {}
    revs = []
    by_ch: dict[str, list[dict]] = defaultdict(list)
    for d in docs:
        by_ch[d["channel"]].append(d)
    for ch in sorted(by_ch):
        lines = []
        for i, d in enumerate(sorted(by_ch[ch], key=lambda x: x["ts"])):
            r = _rev("chat", d["doc_key"], "slack", d["external_id"], f"chat/{ch}.jsonl#{i}", d["title"],
                     f"https://chat.example/{ch}/{d['ts']}", d["ts"], d["author"], d["distractors"])
            b = Buf()
            _write_sentences(W, b, r, d["revisions"][0]["paragraphs"][0], d["ts"], "chat", 1, paraphrase)
            r["content"] = r["prose"] = b.text()
            msg = {"channel": ch, "ts": d["ts"], "author": d["author"], "text": r["content"]}
            if d.get("thread_ts") is not None:
                msg["thread_ts"] = d["thread_ts"]
            lines.append(json.dumps(msg, ensure_ascii=False))
            revs.append(r)
        files[f"chat/{ch}.jsonl"] = "\n".join(lines) + "\n"
    return files, revs


# world

def _auto_tags(W, revs: list[dict]) -> None:
    keys = {t["key"] for t in W.tickets} | {d["number"] for d in W.decisions}
    dup_terms = []
    for pair in W.near_dup_pairs:
        for eid in pair:
            e = W.ent(eid)
            dup_terms += [e["name"]] + e["aliases"]
    dup_res = [word_re(t) for t in dup_terms]
    for r in revs:
        text = r["prose"]
        if not text:
            continue
        if any(k in keys for k in KEY_RE.findall(text)) and "hyphen_id" not in r["distractors"]:
            r["distractors"].append("hyphen_id")
        if any(rx.search(text) for rx in dup_res) and "near_dup_name" not in r["distractors"]:
            r["distractors"].append("near_dup_name")


def render_world(W, paraphrase: bool = False) -> tuple[dict[str, str], list[dict]]:
    files: dict[str, str] = {}
    revs: list[dict] = []
    for t in _revision_dates(W, _intervals(W, ("MEMBER_OF", "LEADS"))):
        revs.append(render_roster(W, t))
    for t in _revision_dates(W, _intervals(W, ("OWNS", "PART_OF", "DEPENDS_ON"))):
        revs.append(render_catalog(W, t))
    for d in W.decisions:
        revs += render_adr(W, d)
    for t in W.tickets:
        revs.append(render_ticket(W, t))
    for d in W.docs:
        if d["kind"] in ("wiki", "meeting"):
            revs += render_prose_doc(W, d, paraphrase)
    chat_files, chat_revs = render_chat(W, [d for d in W.docs if d["kind"] == "chat"], paraphrase)
    for r in revs:
        if r["path"] in files:
            raise GenerationError(f"two revisions render to {r['path']}")
        files[r["path"]] = r["content"]
    files.update(chat_files)
    revs += chat_revs
    _auto_tags(W, revs)
    return files, revs


def build_manifest(W, revs: list[dict]) -> dict:
    docs = []
    for r in sorted(revs, key=lambda r: (r["kind"], r["doc_key"], r["updated_at"])):
        sentences = []
        for c in r["claims"]:
            for ref, states in c["refs"]:
                sentences.append({"ref": ref, "char_start": c["char_start"], "char_end": c["char_end"],
                                  "states": states, "text": c["text"]})
        sentences += [dict(x) for x in r["extras"]]
        sentences.sort(key=lambda s: (s["char_start"], s["ref"], s["states"]))
        docs.append({"doc_key": r["doc_key"], "kind": r["kind"], "path": r["path"], "system": r["system"],
                     "external_id": r["external_id"], "title": r["title"], "uri": r["uri"],
                     "created_at": r["created_at"], "updated_at": r["updated_at"], "author_id": r["author_id"],
                     "phase": r["phase"], "sentences": sentences, "distractors": sorted(r["distractors"])})
    return {"seed": W.seed, "today": W.company["today"], "D_transfer": W.D_transfer, "D_reorg": W.D_reorg,
            "documents": docs}
