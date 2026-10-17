"""Connectors for a workspace's own sources (item 24 step 4): Slack, Linear, GitHub, Jira and docs.

Every connector yields the same `Item`: source kind, external id, permalink, author, timestamp, channel or
project, and text, plus the structured bits a ticket or CODEOWNERS file carries. `to_docs` turns items into
the pipeline's SourceDocs, so ingest goes through the existing pipeline and extractor:

- people, teams, systems and projects the items name become entities, declared by one roster-style doc per
  sync (only structured sources create entities, and a fact needs its entities to exist);
- an issue or PR becomes a ticket doc with ASSIGNED_TO, HAS_STATE and ABOUT facts, its comments as prose;
- CODEOWNERS becomes a catalogue doc with OWNS facts;
- a message or doc page is prose, authored by its person.

Network access goes through an httpx.Client the caller passes in; tests pass one with a MockTransport over
recorded payloads. Keys and OAuth apps are the user's (placeholders until set); tokens are never logged.
"""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from typing import Iterator

import httpx

from .connectors import SourceDoc, StructuredFact, Unit, _paragraph_units, iso_ms


@dataclass
class Item:
    kind: str                 # chat | ticket | doc | code_owners
    system: str               # slack | linear | github | jira | upload
    external_id: str
    url: str                  # permalink to where it was written ("" if none)
    author: str               # display name
    ts: int                   # epoch ms
    channel: str              # channel, team or project
    title: str
    text: str
    assignee: str = ""
    state: str = ""
    about: list[str] = field(default_factory=list)          # systems or components the ticket is about
    team: str = ""
    comments: list[dict] = field(default_factory=list)      # {author, ts, text, url}
    owners: list[tuple[str, str]] = field(default_factory=list)   # CODEOWNERS (owner, system)
    members: dict[str, list[str]] = field(default_factory=dict)   # team -> people (Linear teams)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "x"


def person_id(name: str) -> str:
    return "person:" + _slug(name)


def _owner_id(owner: str) -> str:
    """A CODEOWNERS owner: "@org/team" is a team, "@user" or an email a person."""
    o = owner.lstrip("@")
    return "team:" + _slug(o.split("/", 1)[1]) if "/" in o else person_id(o.split("@", 1)[0])


def _name(eid: str) -> str:
    return eid.split(":", 1)[1].replace("-", " ").title()


# items -> SourceDocs

def to_docs(items: list[Item], system: str) -> list[SourceDoc]:
    people: dict[str, dict] = {}
    teams: dict[str, dict] = {}
    things: dict[str, dict] = {}

    def person(name: str) -> str:
        if not name:
            return ""
        pid = person_id(name)
        people.setdefault(pid, {"id": pid, "name": name, "aliases": [name]})
        return pid

    def thing(name: str, kind: str = "system") -> str:
        eid = f"{kind}:{_slug(name)}"   # "ledger-service" is also asked about as "Ledger Service"
        things.setdefault(eid, {"id": eid, "name": name, "aliases": list(dict.fromkeys([name, name.replace("-", " ").replace("_", " ")]))})
        return eid

    docs: list[SourceDoc] = []
    member_facts: list[tuple[str, StructuredFact]] = []
    t_first = min((i.ts for i in items), default=0)
    for it in items:
        for team, names in it.members.items():
            tid = "team:" + _slug(team)
            teams.setdefault(tid, {"id": tid, "name": team, "aliases": [team]})
            for n in names:
                member_facts.append((f"{n} is a member of {team}", StructuredFact("MEMBER_OF", person(n), tid, valid_from=t_first)))
        if it.kind == "chat":
            docs.append(_chat(it, person(it.author)))
        elif it.kind == "doc":
            docs.append(_page(it, person(it.author)))
        elif it.kind == "ticket":
            docs.append(_ticket(it, person, thing))
        elif it.kind == "code_owners":
            facts = []
            for owner, sysname in it.owners:
                oid = _owner_id(owner)
                if oid.startswith("team:"):
                    teams.setdefault(oid, {"id": oid, "name": _name(oid), "aliases": [owner.lstrip("@")]})
                else:
                    people.setdefault(oid, {"id": oid, "name": owner.lstrip("@"), "aliases": [owner.lstrip("@")]})
                facts.append((f"{owner} owns {sysname}", StructuredFact("OWNS", oid, thing(sysname), valid_from=it.ts)))
            docs.append(_facts_doc(it, "catalog", facts))
    if member_facts:
        docs.append(_facts_doc(Item("roster", system, "members", "", "", t_first, "", f"{system} teams", ""), "roster", member_facts))
    ents = [*teams.values(), *people.values(), *things.values()]
    if ents:   # the entities every other doc's facts and authors point at, declared up front
        text = "\n".join(f"- {e['name']} ({e['id'].split(':', 1)[0]})" for e in ents)
        d = SourceDoc(f"roster:{system}:directory", "roster", system, "directory", f"People, teams and systems from {system}",
                      "", t_first, t_first, "", text)
        d.entities = ents
        docs.insert(0, d)
    return docs


def _meta_doc(it: Item, kind: str, text: str, author: str = "") -> SourceDoc:
    return SourceDoc(f"{kind}:{it.system}:{it.external_id}", kind, it.system, it.external_id, it.title, it.url,
                     it.ts, it.ts, author, text)


def _chat(it: Item, author: str) -> SourceDoc:
    d = _meta_doc(it, "chat", it.text, author)
    d.units = [Unit(it.text, 0, len(it.text), it.ts, it.channel, author_id=author)]
    return d


def _page(it: Item, author: str) -> SourceDoc:
    d = _meta_doc(it, "wiki", it.text, author)
    d.units = _paragraph_units(it.text, it.ts, author=author)
    return d


def _facts_doc(it: Item, kind: str, facts: list[tuple[str, StructuredFact]]) -> SourceDoc:
    text, units = "", []
    for line, f in facts:
        s = len(text)
        text += line + "\n"
        units.append(Unit(line, s, s + len(line), it.ts, it.title, structured=[f], prose=False, phase=1))
    d = _meta_doc(it, kind, text)
    d.units = units
    return d


def _ticket(it: Item, person, thing) -> SourceDoc:
    tid = "ticket:" + _slug(it.external_id)
    text, units = "", []

    def add(line: str, ts: int, **kw) -> None:
        nonlocal text
        s = len(text)
        text += line + "\n\n"
        units.append(Unit(line, s, s + len(line), ts, kw.pop("heading", "ticket"), **kw))
    add(f"{it.external_id}: {it.title}\n\n{it.text}".strip(), it.ts)
    if it.assignee:
        add(f"{it.external_id} is assigned to {it.assignee}", it.ts, heading="history", prose=False, phase=1,
            structured=[StructuredFact("ASSIGNED_TO", tid, person(it.assignee), valid_from=it.ts)])
    if it.state:
        add(f"{it.external_id} state is {it.state}", it.ts, heading="history", prose=False, phase=1,
            structured=[StructuredFact("HAS_STATE", tid, object_value=it.state.lower(), valid_from=it.ts)])
    for a in it.about:   # "project:<name>" for a project (Linear), else a system or component
        kind, _, name = a.rpartition(":") if a.startswith("project:") else ("system", "", a)
        add(f"{it.external_id} is about {name}", it.ts, heading="history", prose=False, phase=1,
            structured=[StructuredFact("ABOUT", tid, thing(name, kind), valid_from=it.ts)])
    for c in it.comments:
        add(f"{c['author']} commented: {c['text']}", c["ts"], heading="comments", author_id=person(c["author"]))
    d = _meta_doc(it, "ticket", text, person(it.author))
    d.ticket_id = tid
    d.units = units
    d.entities = [{"id": tid, "name": it.external_id, "aliases": [it.external_id], "key": it.external_id,
                   "title": it.title, "description": it.title}]
    return d


# connectors

@dataclass
class Connector:
    kind: str
    label: str
    needs: list[str]             # what the user must provide (env for OAuth apps, fields for keys)
    fields: list[str]            # what the connect form asks for

    def fetch(self, http: httpx.Client, cfg: dict) -> Iterator[Item]:
        raise NotImplementedError


class Slack(Connector):
    """Messages and threads of the chosen channels, each with its permalink (conversations.history/replies)."""

    def fetch(self, http, cfg):
        h = {"Authorization": f"Bearer {cfg['token']}"}
        team = http.get("https://slack.com/api/auth.test", headers=h).json()
        base = (team.get("url") or "https://slack.com/").rstrip("/")
        users = {u["id"]: (u.get("real_name") or (u.get("profile") or {}).get("real_name") or u.get("name", ""))
                 for u in http.get("https://slack.com/api/users.list", headers=h).json().get("members", [])}
        for ch in cfg.get("channels") or []:
            name = ch.lstrip("#")
            hist = http.get("https://slack.com/api/conversations.history", headers=h, params={"channel": name}).json()
            for m in hist.get("messages", []):
                msgs = [m]
                if m.get("reply_count"):
                    msgs += http.get("https://slack.com/api/conversations.replies", headers=h,
                                     params={"channel": name, "ts": m["ts"]}).json().get("messages", [])[1:]
                for x in msgs:
                    if x.get("subtype") or not (x.get("text") or "").strip():
                        continue
                    text = re.sub(r"<@(\w+)>", lambda u: "@" + users.get(u.group(1), u.group(1)), x["text"])
                    yield Item("chat", "slack", f"{name}/{x['ts']}", f"{base}/archives/{name}/p{x['ts'].replace('.', '')}",
                               users.get(x.get("user", ""), x.get("user", "")), int(float(x["ts"]) * 1000), name,
                               f"#{name} message", text)


LINEAR_QUERY = """query { issues(first: 100) { nodes { identifier title description url createdAt
  state { name } assignee { name } creator { name } project { name } team { name members { nodes { name } } }
  comments { nodes { body url createdAt user { name } } } } } }"""


class Linear(Connector):
    """Issues with their state, assignee, project and comments, and team membership (GraphQL API)."""

    def fetch(self, http, cfg):
        r = http.post("https://api.linear.app/graphql", headers={"Authorization": cfg["token"]}, json={"query": LINEAR_QUERY})
        for n in r.json()["data"]["issues"]["nodes"]:
            team = (n.get("team") or {}).get("name", "")
            members = [m["name"] for m in ((n.get("team") or {}).get("members") or {}).get("nodes", [])]
            yield Item("ticket", "linear", n["identifier"], n["url"], (n.get("creator") or {}).get("name", ""),
                       iso_ms(n["createdAt"]), team, n["title"], n.get("description") or "",
                       assignee=(n.get("assignee") or {}).get("name", ""), state=(n.get("state") or {}).get("name", ""),
                       about=["project:" + n["project"]["name"]] if n.get("project") else [], team=team,
                       comments=[{"author": (c.get("user") or {}).get("name", ""), "ts": iso_ms(c["createdAt"]),
                                  "text": c["body"], "url": c.get("url", "")} for c in (n.get("comments") or {}).get("nodes", [])],
                       members={team: members} if team and members else {})


class GitHub(Connector):
    """Issues and PRs with comments and review comments, and CODEOWNERS as ownership (REST API)."""

    def fetch(self, http, cfg):
        repo = cfg["repo"].strip("/")
        h = {"Authorization": f"Bearer {cfg['token']}", "Accept": "application/vnd.github+json"}
        api = f"https://api.github.com/repos/{repo}"
        system = repo.split("/")[-1]
        for path in (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"):
            r = http.get(f"{api}/contents/{path}", headers=h)
            if r.status_code == 200:
                body = r.json()
                text = base64.b64decode(body["content"]).decode()
                rules = [line.split() for line in text.splitlines() if line.strip() and not line.startswith("#")]
                # the repo's owner is its catch-all rule; a path rule owns that path, not the system
                top = next((r for r in reversed(rules) if r[0] == "*"), rules[0] if rules else [])
                owners = [(o, system) for o in top[1:] if o.startswith("@")]
                yield Item("code_owners", "github", f"{repo}/CODEOWNERS", body.get("html_url", ""), "", iso_ms(cfg.get("since", "2025-01-01")),
                           repo, f"{repo} CODEOWNERS", text, owners=list(dict.fromkeys(owners)))
                break
        review: dict[int, list[dict]] = {}
        for c in http.get(f"{api}/pulls/comments", headers=h).json():
            n = int(c["pull_request_url"].rsplit("/", 1)[1])
            review.setdefault(n, []).append({"author": c["user"]["login"], "ts": iso_ms(c["created_at"]),
                                             "text": c["body"], "url": c["html_url"]})
        for i in http.get(f"{api}/issues", headers=h, params={"state": "all"}).json():
            comments = [{"author": c["user"]["login"], "ts": iso_ms(c["created_at"]), "text": c["body"], "url": c["html_url"]}
                        for c in http.get(i["comments_url"], headers=h).json()] if i.get("comments") else []
            kind = "PR" if i.get("pull_request") else "issue"
            yield Item("ticket", "github", f"{system}#{i['number']}", i["html_url"], i["user"]["login"], iso_ms(i["created_at"]),
                       repo, f"{kind} {i['title']}", i.get("body") or "",
                       assignee=(i.get("assignee") or {}).get("login", ""), state=i["state"], about=[system],
                       comments=comments + review.get(i["number"], []))


def _adf_text(node) -> str:
    """Jira's Atlassian Document Format as plain text."""
    if isinstance(node, str) or node is None:
        return node or ""
    if node.get("type") == "text":
        return node.get("text", "")
    sep = "\n\n" if node.get("type") in ("doc",) else ""
    return sep.join(_adf_text(c) for c in node.get("content", []))


class Jira(Connector):
    """Issues with assignee, status, components and comments (REST API v3), each with its browse URL."""

    def fetch(self, http, cfg):
        site = cfg["site"].rstrip("/")
        auth = base64.b64encode(f"{cfg['email']}:{cfg['token']}".encode()).decode()
        r = http.get(f"{site}/rest/api/3/search", headers={"Authorization": f"Basic {auth}", "Accept": "application/json"},
                     params={"jql": cfg.get("jql") or "order by updated desc",
                             "fields": "summary,description,assignee,reporter,status,components,comment,created,project"})
        for i in r.json().get("issues", []):
            f = i["fields"]
            yield Item("ticket", "jira", i["key"], f"{site}/browse/{i['key']}", (f.get("reporter") or {}).get("displayName", ""),
                       iso_ms(f["created"]), (f.get("project") or {}).get("name", ""), f["summary"], _adf_text(f.get("description")),
                       assignee=(f.get("assignee") or {}).get("displayName", ""), state=(f.get("status") or {}).get("name", ""),
                       about=[c["name"] for c in f.get("components") or []],
                       comments=[{"author": (c.get("author") or {}).get("displayName", ""), "ts": iso_ms(c["created"]),
                                  "text": _adf_text(c.get("body")), "url": f"{site}/browse/{i['key']}?focusedCommentId={c['id']}"}
                                 for c in ((f.get("comment") or {}).get("comments") or [])])


CONNECTORS: dict[str, Connector] = {
    "slack": Slack("slack", "Slack", ["SLACK_CLIENT_ID", "SLACK_CLIENT_SECRET", "SLACK_REDIRECT_URL"], ["channels"]),
    "linear": Linear("linear", "Linear", [], ["token"]),
    "github": GitHub("github", "GitHub", [], ["token", "repo"]),
    "jira": Jira("jira", "Jira", [], ["site", "email", "token", "jql"]),
}


def fetch_docs(kind: str, cfg: dict, http: httpx.Client) -> list[SourceDoc]:
    return to_docs(list(CONNECTORS[kind].fetch(http, cfg)), kind)

