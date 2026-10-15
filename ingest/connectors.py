"""Connectors for the rendered world (05 §1, docs/render-contract.md).

Each connector turns one file (or one chat line) into a `SourceDoc`: the Source's own text, its
span units with offsets, the entities it defines (structured sources only) and the structured
candidates of each unit. Prose units are left for extraction.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from brain import ids
from brain.config import MAX


def iso_ms(v) -> int:
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, datetime):
        return int(v.replace(tzinfo=v.tzinfo or timezone.utc).timestamp() * 1000)
    if isinstance(v, date):
        return int(datetime(v.year, v.month, v.day, tzinfo=timezone.utc).timestamp() * 1000)
    s = str(v).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        d = date.fromisoformat(s)
        return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000)


@dataclass
class StructuredFact:
    predicate: str
    subject_id: str
    object_id: str = ""
    object_value: str = ""
    qualifier: str = ""
    negated: bool = False
    valid_from: int = 0
    basis: str = "stated"


@dataclass
class Unit:
    text: str
    char_start: int
    char_end: int
    ts: int
    heading_path: str = ""
    author_id: str = ""
    author_role: str = "human"
    structured: list[StructuredFact] = field(default_factory=list)
    prose: bool = True          # eligible for extraction
    section: str = ""           # ADR body section (context / decision / consequences)
    phase: int = 2


@dataclass
class SourceDoc:
    doc_key: str
    kind: str
    system: str
    external_id: str
    title: str
    uri: str
    created_at: int
    updated_at: int
    author_id: str
    text: str
    units: list[Unit] = field(default_factory=list)
    entities: list[dict] = field(default_factory=list)
    decision_id: str = ""
    ticket_id: str = ""
    attendees: list[str] = field(default_factory=list)

    @property
    def phase(self) -> int:
        return 1 if self.kind in ("roster", "catalog", "adr", "ticket") else 2

    @property
    def source_id(self) -> str:
        return ids.source_id(self.doc_key, self.updated_at, self.text)


def _paragraph_units(text: str, ts: int, base: int = 0, author: str = "", role: str = "human",
                     skip_headings: bool = True) -> list[Unit]:
    """One Markdown paragraph or list item per unit, with the heading trail."""
    units: list[Unit] = []
    heading: list[str] = []
    pos = 0
    for block in re.split(r"(\n\s*\n)", text):
        start = pos
        pos += len(block)
        if not block.strip() or re.fullmatch(r"\n\s*\n", block):
            continue
        lines = block.split("\n")
        off = start
        buf: list[tuple[int, str]] = []

        def flush():
            if buf:
                s0 = buf[0][0]
                e0 = buf[-1][0] + len(buf[-1][1])
                t = text[s0:e0]
                if t.strip():
                    units.append(Unit(t, base + s0, base + e0, ts, " > ".join(heading), author, role))
                buf.clear()

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                flush()
                level = len(stripped) - len(stripped.lstrip("#"))
                heading[:] = heading[:level - 1] + [stripped.lstrip("#").strip()]
            elif re.match(r"\s*([-*]|\d+\.)\s+", line):
                flush()
                buf.append((off, line))
                flush()
            elif stripped.startswith("|") or not stripped or stripped.lower().startswith("attendees:"):
                flush()
            else:
                buf.append((off, line))
            off += len(line) + 1
        flush()
    return units


def _table_rows(text: str):
    """Yield (team_heading, cells, start, end) for Markdown table data rows."""
    section = ""
    pos = 0
    header: list[str] | None = None
    for line in text.split("\n"):
        start, end = pos, pos + len(line)
        pos = end + 1
        s = line.strip()
        if s.startswith("#"):
            section = s.lstrip("#").strip()
            header = None
            continue
        if not s.startswith("|"):
            header = None if not s else header
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if header is None:
            header = cells
            continue
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
            continue
        yield section, dict(zip(header, cells)), start, end


def roster(path: Path, meta: dict) -> SourceDoc:
    text = path.read_text()
    ts = meta["updated_at"]
    doc = _doc(meta, text)
    teams, people = {}, {}
    for section, row, s, e in _table_rows(text):
        m = re.match(r"Team:\s*(.+?)\s*\((team:[\w-]+)\)", section)
        if section.lower() == "people" and "ID" in row:
            people[row["ID"]] = {"id": row["ID"], "name": row.get("Name", ""), "title": row.get("Title", ""),
                                 "aliases": [a.strip() for a in row.get("Aliases", "").split(";") if a.strip()]}
            continue
        if section.lower() == "teams" and "ID" in row:
            teams[row["ID"]] = {"id": row["ID"], "name": row.get("Name", ""),
                                "aliases": [a.strip() for a in row.get("Aliases", "").split(";") if a.strip()]}
            continue
        if m and "ID" in row:
            tid = m.group(2)
            teams.setdefault(tid, {"id": tid, "name": m.group(1), "aliases": []})
            pid, frm = row["ID"], iso_ms(row["From"])
            facts = []
            if row.get("Role", "").lower() == "lead":
                facts.append(StructuredFact("LEADS", pid, tid, valid_from=frm))
            if row.get("Primary", "").lower() == "yes":
                facts.append(StructuredFact("MEMBER_OF", pid, tid, qualifier="primary", valid_from=frm))
            elif row.get("Primary", "").lower() == "no":
                facts.append(StructuredFact("MEMBER_OF", pid, tid, valid_from=frm))
            doc.units.append(Unit(text[s:e], s, e, ts, section, structured=facts, prose=False, phase=1))
    for u in _paragraph_units(text, ts):
        doc.units.append(u)  # roster prose: rank 2, phase 2
    doc.entities = [*teams.values(), *people.values()]
    for ent in doc.entities:
        ent["created_from"] = doc.source_id
    return doc


def catalog(path: Path, meta: dict) -> SourceDoc:
    text = path.read_text()
    ts = meta["updated_at"]
    doc = _doc(meta, text)
    data = yaml.safe_load(text) or {}
    lines = text.split("\n")
    starts = []
    pos = 0
    for line in lines:
        m = re.match(r"\s*-\s+id:\s*(\S+)", line)
        if m:
            starts.append((pos, m.group(1)))
        elif re.match(r"^\S", line) and starts and starts[-1][1] != "__top__":
            starts.append((pos, "__top__"))
        pos += len(line) + 1
    spans: dict[str, tuple[int, int]] = {}
    for i, (s, eid) in enumerate(starts):
        if eid == "__top__":
            continue
        e = starts[i + 1][0] if i + 1 < len(starts) else len(text)
        spans[eid] = (s, len(text[:e].rstrip()))
    for kind in ("projects", "systems"):
        for ent in data.get(kind, []) or []:
            eid = ent["id"]
            info = {"id": eid, "name": ent.get("name", eid), "aliases": list(ent.get("aliases") or []),
                    "created_from": doc.source_id}
            if kind == "systems":
                info["tier"] = int(ent.get("tier", 3))
            doc.entities.append(info)
            facts = []
            if ent.get("owner"):
                facts.append(StructuredFact("OWNS", ent["owner"], eid,
                                            valid_from=iso_ms(ent.get("owner_from", ts))))
            if kind == "systems" and ent.get("project"):
                facts.append(StructuredFact("PART_OF", eid, ent["project"],
                                            valid_from=iso_ms(ent.get("project_from", ts))))
            for d in ent.get("depends_on") or []:
                facts.append(StructuredFact("DEPENDS_ON", eid, d["id"], valid_from=iso_ms(d.get("from", ts))))
            for d in ent.get("dropped_depends_on") or []:
                facts.append(StructuredFact("DEPENDS_ON", eid, d["id"], negated=True, valid_from=iso_ms(d["at"])))
            s, e = spans.get(eid, (0, len(text)))
            doc.units.append(Unit(text[s:e], s, e, ts, kind, structured=facts, prose=False, phase=1))
    return doc


def adr(path: Path, meta: dict) -> SourceDoc:
    text = path.read_text()
    ts = meta["updated_at"]
    doc = _doc(meta, text)
    m = re.match(r"---\n(.*?)\n---\n?", text, re.S)
    fm = yaml.safe_load(m.group(1)) if m else {}
    number = str(fm.get("number", meta.get("external_id")))
    did = "decision:" + number.lower()
    doc.decision_id = did
    status = str(fm.get("status", "proposed"))
    st_from = ts if status == "superseded" else iso_ms(fm.get("date", ts))
    facts = [StructuredFact("HAS_STATUS", did, object_value=status, valid_from=st_from)]
    dfrom = iso_ms(fm.get("date", ts))
    for d in fm.get("deciders") or []:
        facts.append(StructuredFact("DECIDED_BY", did, d, valid_from=dfrom))
    for a in fm.get("affects") or []:
        facts.append(StructuredFact("AFFECTS", did, a, valid_from=dfrom))
    for r in fm.get("replaces") or []:
        facts.append(StructuredFact("REPLACES", did, "decision:" + str(r).lower(), valid_from=dfrom))
    if m:
        doc.units.append(Unit(text[:m.end()].rstrip("\n"), 0, len(text[:m.end()].rstrip("\n")), ts,
                              "front matter", structured=facts, prose=False, phase=1))
    body_start = m.end() if m else 0
    for u in _paragraph_units(text[body_start:], ts, base=body_start):
        u.section = u.heading_path.split(" > ")[0].lower() if u.heading_path else ""
        doc.units.append(u)
    doc.entities = [{"id": did, "name": number, "aliases": [number, number.replace("-", "")],
                     "number": number, "title": fm.get("title", ""), "decided_at": dfrom,
                     "description": fm.get("title", ""), "created_from": doc.source_id}]
    doc.title = f"{number}: {fm.get('title', '')}"
    return doc


def _json_rows(raw: str, key: str) -> list[tuple[int, int]]:
    """Offsets of the row objects inside the array `key` of a ticket file (rows have no nested braces)."""
    i = raw.find(f'"{key}"')
    if i < 0:
        return []
    j = raw.find("[", i)
    end = raw.find("]", j)
    return [(m.start() + j, m.end() + j) for m in re.finditer(r"\{[^{}]*\}", raw[j:end])]


def ticket(path: Path, meta: dict) -> SourceDoc:
    raw = path.read_text()
    data = json.loads(raw)
    key = data["key"]
    tid = "ticket:" + key.lower()
    parts: list[tuple[str, dict]] = []
    parts.append((f"{key}: {data.get('title', '')}\n\n{data.get('description', '')}".strip(),
                  {"kind": "prose", "ts": meta["created_at"] or meta["updated_at"]}))
    for row in data.get("assignee_history") or []:
        parts.append((f"{key} assignee changed to {row['who']} on {row['at']}",
                      {"kind": "fact", "fact": StructuredFact("ASSIGNED_TO", tid, row["who"],
                                                              valid_from=iso_ms(row["at"])),
                       "ts": iso_ms(row["at"])}))
    for row in data.get("state_history") or []:
        parts.append((f"{key} state changed to {row['state']} on {row['at']}",
                      {"kind": "fact", "fact": StructuredFact("HAS_STATE", tid, object_value=row["state"],
                                                              valid_from=iso_ms(row["at"])),
                       "ts": iso_ms(row["at"])}))
    prev = None
    for row in data.get("component_history") or []:
        facts = [StructuredFact("ABOUT", tid, row["about"], valid_from=iso_ms(row["at"]))]
        if prev and prev != row["about"]:  # A65: a replacement closes the old component
            facts.append(StructuredFact("ABOUT", tid, prev, negated=True, valid_from=iso_ms(row["at"])))
        parts.append((f"{key} component set to {row['about']} on {row['at']}",
                      {"kind": "facts", "facts": facts, "ts": iso_ms(row["at"])}))
        prev = row["about"]
    for c in data.get("comments") or []:
        parts.append((f"{c['author']} commented on {c['at']}: {c['text']}",
                      {"kind": "comment", "author": c["author"], "ts": iso_ms(c["at"]), "body": c["text"]}))
    # The Source text is the file itself, so span offsets match the manifest and the viewer highlights
    # the row; each span's text is a readable rendering of its row.
    t0 = raw.find('"title"')
    d0 = raw.find('"description"')
    d1 = raw.find("\n", d0) if d0 >= 0 else -1
    offsets = [(t0, d1 if d1 > 0 else len(raw))]
    for k in ("assignee_history", "state_history", "component_history", "comments"):
        offsets += _json_rows(raw, k)
    doc = _doc(meta, raw)
    doc.ticket_id = tid
    doc.title = f"{key}: {data.get('title', '')}"
    for (p, info), (s, e) in zip(parts, offsets):
        if info["kind"] == "prose":
            doc.units.append(Unit(p, s, e, info["ts"], "ticket"))
        elif info["kind"] == "fact":
            doc.units.append(Unit(p, s, e, info["ts"], "history", structured=[info["fact"]], prose=False, phase=1))
        elif info["kind"] == "facts":
            doc.units.append(Unit(p, s, e, info["ts"], "history", structured=info["facts"], prose=False, phase=1))
        else:
            doc.units.append(Unit(p, s, e, info["ts"], "comments", author_id=info["author"]))
    doc.entities = [{"id": tid, "name": key, "aliases": [key, key.replace("-", "")], "key": key,
                     "title": data.get("title", ""), "description": data.get("title", ""),
                     "created_from": doc.source_id}]
    return doc


def wiki(path: Path, meta: dict) -> SourceDoc:
    text = path.read_text()
    doc = _doc(meta, text)
    doc.units = _paragraph_units(text, meta["updated_at"], author=meta.get("author_id", ""))
    return doc


def meeting(path: Path, meta: dict) -> SourceDoc:
    text = path.read_text()
    doc = _doc(meta, text)
    m = re.search(r"^Attendees:\s*(.+)$", text, re.M)
    if m:
        doc.attendees = [a.strip() for a in m.group(1).split(",") if a.strip()]
    doc.units = _paragraph_units(text, meta["updated_at"], author=meta.get("author_id", ""))
    return doc


def chat_message(line: dict, meta: dict) -> SourceDoc:
    text = line["text"]
    doc = _doc(meta, text)
    ts = iso_ms(line["ts"]) if not isinstance(line["ts"], (int, float)) else int(line["ts"])
    doc.units = [Unit(text, 0, len(text), ts, line.get("channel", ""), author_id=line.get("author", ""))]
    return doc


def _doc(meta: dict, text: str) -> SourceDoc:
    return SourceDoc(meta["doc_key"], meta["kind"], meta.get("system", ""), meta.get("external_id", ""),
                     meta.get("title", ""), meta.get("uri", ""), int(meta.get("created_at") or 0),
                     int(meta["updated_at"]), meta.get("author_id", "") or "", text)


READERS = {"roster": roster, "catalog": catalog, "adr": adr, "ticket": ticket, "wiki": wiki, "meeting": meeting}


def read_render(render_dir: Path) -> list[SourceDoc]:
    manifest = json.loads((render_dir / "manifest.json").read_text())
    docs: list[SourceDoc] = []
    chat_cache: dict[str, list[dict]] = {}
    for meta in manifest["documents"]:
        path = meta["path"]
        if meta["kind"] == "chat":
            file, _, idx = path.partition("#")
            if file not in chat_cache:
                chat_cache[file] = [json.loads(x) for x in (render_dir / file).read_text().splitlines() if x.strip()]
            docs.append(chat_message(chat_cache[file][int(idx)], meta))
        else:
            docs.append(READERS[meta["kind"]](render_dir / path, meta))
    return docs



# Uploads: Markdown / plain text as a wiki page, a Slack export as chat messages (same shapes as the world's)

def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "upload"


def _slack(channel: str, msgs: list[dict], users: dict[str, str]) -> list[SourceDoc]:
    """One chat SourceDoc per message; joins, bot and edit events (any subtype) are skipped. author_id is
    the Slack display name here: the pipeline resolves it to a Person id."""
    docs = []
    for m in msgs:
        if m.get("type") != "message" or m.get("subtype") or not (m.get("text") or "").strip():
            continue
        ts = int(float(m["ts"]) * 1000)
        text = re.sub(r"<@(\w+)>", lambda x: "@" + users.get(x.group(1), x.group(1)), m["text"])
        author = users.get(m.get("user", "")) or (m.get("user_profile") or {}).get("real_name", "")
        meta = {"doc_key": f"chat:slack:{channel}/{ts}", "kind": "chat", "system": "slack",
                "external_id": f"{channel}/{ts}", "title": f"#{channel} message", "uri": "",
                "created_at": ts, "updated_at": ts, "author_id": author}
        docs.append(chat_message({"channel": channel, "ts": ts, "author": author, "text": text}, meta))
    return docs


def upload_docs(name: str, data: bytes, now: int) -> list[SourceDoc]:
    """`.md`/`.markdown`/`.txt` -> one wiki page; a Slack channel export `.json` (a message list) or a
    whole export `.zip` (`<channel>/<day>.json` plus `users.json`) -> one chat message each."""
    low = name.lower()
    if low.endswith((".md", ".markdown", ".txt")):
        text = data.decode("utf-8")
        stem = Path(name).stem
        h = re.search(r"^#\s+(.+)$", text, re.M)
        meta = {"doc_key": f"wiki:upload:{_slug(stem)}", "kind": "wiki", "system": "upload", "external_id": _slug(stem),
                "title": h.group(1).strip() if h else stem, "uri": "", "created_at": now, "updated_at": now,
                "author_id": ""}
        doc = _doc(meta, text)
        doc.units = _paragraph_units(text, now)
        return [doc]
    if low.endswith(".json"):
        p = Path(name)
        return _slack(_slug(p.parent.name if p.parent.name else p.stem), json.loads(data), {})
    if low.endswith(".zip"):
        z = zipfile.ZipFile(io.BytesIO(data))
        files = [n for n in z.namelist() if n.endswith(".json")]
        users_file = next((n for n in files if Path(n).name == "users.json"), None)
        users = {u["id"]: u.get("real_name") or (u.get("profile") or {}).get("real_name") or u.get("name", "")
                 for u in json.loads(z.read(users_file))} if users_file else {}
        docs = []
        for n in sorted(files):
            if Path(n).parent.name and Path(n).name not in ("users.json", "channels.json", "integration_logs.json"):
                docs += _slack(_slug(Path(n).parent.name), json.loads(z.read(n)), users)
        return docs
    raise ValueError(f"unsupported upload {name!r}: use .md, .markdown, .txt, a Slack .json or an export .zip")

__all__ = ["SourceDoc", "Unit", "StructuredFact", "read_render", "upload_docs", "iso_ms", "MAX"]
