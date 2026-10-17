"""Two-phase ingestion pipeline (05 §2, A58).

Phase 1: structured sources (roster, catalogue, ADR front matter, ticket fields), so every entity
exists first. Phase 2: everything else, plus the prose parts of phase-1 sources. Within a phase
the order is free; the shuffled test permutes it. A Source counts as ingested only once its
completion marker `ingested_at` is set after every stage succeeded.
"""
from __future__ import annotations

import json
import os
import random
from concurrent.futures import ThreadPoolExecutor
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from brain import ids, providers, registry, store
from brain.config import MAX
from brain.db import Graph
from brain.write_path import Candidate, ValidationError, WritePath, validate

from .connectors import SourceDoc, Unit, iso_ms, read_render, upload_docs
from .extract import AliasIndex, extract, extractor_name, screen_injection
from brain.ids import now_ms


EXTRACT_WORKERS = int(os.environ.get("BRAIN_EXTRACT_WORKERS", "8"))


@dataclass
class Report:
    rows: list[dict] = field(default_factory=list)
    skipped: int = 0
    sources: int = 0

    def add(self, **kw) -> None:
        self.rows.append(kw)

    def counts(self) -> dict:
        c: dict[str, int] = defaultdict(int)
        for r in self.rows:
            c[r["outcome"]] += 1
        return dict(c)

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(r, default=str) for r in self.rows))


class Ingestor:
    def __init__(self, g: Graph, clock=now_ms, fail_after_stage8: str | None = None):
        self.g = g
        self.clock = clock
        self.report = Report()
        self.index: AliasIndex | None = None
        self.entities: dict[str, dict] = {}
        self.fail_after_stage8 = fail_after_stage8   # test hook: crash one Source before its marker
        self.live = False             # an upload: the extractor model reads it (item 20 step 0)
        self.screened: set[str] = set()   # Source ids the ingest screen flagged: spans only, no facts
        self.on_doc = None   # progress hook (item 24 ingest jobs): called with (done, total) after each Source

    def ingest_render(self, render_dir: Path, seed: int | None = None) -> Report:
        docs = read_render(Path(render_dir))
        return self.ingest_docs(docs, seed)

    def ingest_upload(self, name: str, data: bytes, url: str = "") -> Report:
        """An uploaded file (connectors.upload_docs) through the same pipeline. Slack display names become
        Person ids where a person has that name or alias; other authors are left empty. `url` is where a
        single document lives, so its citations link back to it (item 24)."""
        docs = upload_docs(name, data, self.clock())
        if url and len(docs) == 1:
            docs[0].uri = url
        self._load_entities()
        people = {n.lower(): eid for eid, e in self.entities.items() if eid.startswith("person:")
                  for n in [e["name"], *e["aliases"]] if n}
        for d in docs:
            if d.author_id and not d.author_id.startswith("person:"):
                d.author_id = people.get(d.author_id.lower(), "")
                for u in d.units:
                    u.author_id = d.author_id
        self.live = True
        for d in docs:
            res = screen_injection("\n\n".join(u.text for u in d.units))
            if res and res["flagged"]:
                self.screened.add(d.source_id)
                self.report.add(source=d.source_id, outcome="injection_screened", model=res["model"], p=res["p"])
            elif res and res.get("skipped"):
                self.report.add(source=d.source_id, outcome="screen_skipped", error=res["skipped"])
        return self.ingest_docs(docs)

    def ingest_docs(self, docs: list[SourceDoc], seed: int | None = None) -> Report:
        rnd = random.Random(seed)
        self._docs_by_sid = {d.source_id: d for d in docs}
        phase1 = [d for d in docs if d.phase == 1]
        phase2 = [d for d in docs if d.phase == 2]
        if seed is not None:
            rnd.shuffle(phase1)
            rnd.shuffle(phase2)
        # Phase 1a: entities from every structured source (only structured sources create entities).
        ents: dict[str, dict] = {}
        for d in sorted(phase1, key=lambda d: (d.updated_at, d.source_id)):
            for e in d.entities:
                ents.setdefault(e["id"], {}).update(e)
        if ents:
            self._upsert_entities(list(ents.values()))
        self._load_entities()
        self._prewarm(phase1 + phase2)
        todo1 = [d for d in phase1 if not self._done(d)]
        for d in phase1:
            if d not in todo1:
                self.report.skipped += 1
        for d in todo1:
            self._ingest(d, stage="structured")
        # Phase 2: text, including the prose parts of phase-1 sources.
        todo = todo1 + [d for d in phase2 if not self._done(d)]
        for i, d in enumerate(todo, 1):
            self._ingest(d, stage="prose")
            if self.on_doc:
                self.on_doc(i, len(todo))
        self._retract_unsupported()
        return self.report

    def _prewarm(self, docs: list[SourceDoc]) -> None:
        """Run LLM extraction for every prose span of every Source in one global pool so the
        per-Source pipeline hits the provider cache. Chat messages are one span each, so without
        this phase 2 would be one slow call at a time. No-op without an LLM."""
        if not self.live or not providers.llm_available() or not self.index:
            return
        types = {k: registry.label_of(k) for k in self.entities}
        names = {k: v["name"] for k, v in self.entities.items()}
        jobs = []
        for d in docs:
            for u in d.units:
                if u.prose and not u.structured:
                    ments = self.index.find(u.text)
                    if ments:
                        jobs.append((u.text, ments))
        with ThreadPoolExecutor(max_workers=EXTRACT_WORKERS) as pool:
            for _ in pool.map(lambda j: _safe_extract(j[0], j[1], types, names, self.live), jobs):
                pass

    def _done(self, d: SourceDoc) -> bool:
        ex = store.source_exists(self.g, d.source_id)
        return bool(ex) and ex["ingested_at"] is not None and ex["ingested_at"] < MAX

    def _upsert_entities(self, ents: list[dict]) -> None:
        clean = []
        for e in ents:
            clean.append({k: v for k, v in e.items() if k != "embedding" and not isinstance(v, (dict,))})
        store.upsert_entities(self.g, clean)
        texts = [f"{e.get('name', '')} {' '.join(e.get('aliases') or [])} {e.get('description', '')}" for e in clean]
        vecs = providers.embed(texts)
        rows = [{"id": e["id"], "e": v} for e, v in zip(clean, vecs)]
        for i in range(0, len(rows), 100):
            self.g.write("UNWIND $rows AS x MATCH (n:Entity {id:x.id}) SET n.embedding = vecf32(x.e)",
                         {"rows": rows[i:i + 100]}, template="entity_embeddings")

    def _load_entities(self) -> None:
        rows = self.g.q("all_entities", timeout=10000)
        self.entities = {r["id"]: {"name": r["name"], "aliases": r["aliases"] or []} for r in rows}
        self.index = AliasIndex([{"id": k, **v} for k, v in self.entities.items()])

    def _ingest(self, d: SourceDoc, stage: str) -> None:
        g, sid = self.g, d.source_id
        now = self.clock()
        becomes_latest, prev_latest = False, None
        if stage == "structured" or d.phase == 2:
            # Step 1: revision, latest by (updated_at, rev) — never by arrival.
            ex = store.source_exists(g, sid)
            if ex and ex["ingested_at"] is not None and ex["ingested_at"] < MAX:
                self.report.skipped += 1
                return
            if not ex:
                store.create_source(g, {"id": sid, "doc_key": d.doc_key, "kind": d.kind, "system": d.system,
                                        "external_id": d.external_id, "title": d.title, "uri": d.uri,
                                        "author_id": d.author_id,
                                        "created_at": d.created_at, "updated_at": d.updated_at,
                                        "ingested_at": MAX, "is_latest": False, "status": "active",
                                        "user_id": ""})
            revs = store.revisions(g, d.doc_key)
            latest = max(revs, key=lambda r: (r["updated_at"], r["id"].rsplit("@", 1)[-1]))
            prev = [r for r in revs if r["is_latest"] and r["id"] != sid]
            if latest["id"] == sid and not any(r["id"] == sid and r["is_latest"] for r in revs):
                becomes_latest = True
                prev_latest = prev[0]["id"] if prev else None
                if prev_latest:
                    store.set_source(g, prev_latest, {"is_latest": False})
                store.set_source(g, sid, {"is_latest": True})
            lower = [r for r in revs if (r["updated_at"], r["id"]) < (d.updated_at, sid)]
            if lower:
                older = max(lower, key=lambda r: (r["updated_at"], r["id"]))
                store.link_revision(g, sid, older["id"])
            self.report.sources += 1
            self._spans(d, becomes_latest or latest["id"] == sid, prev_latest)
            self._prev_latest = getattr(self, "_prev_latest", {})
            self._prev_latest[sid] = (becomes_latest, prev_latest)

        units = [u for u in d.units if (u.phase == 1) == (stage == "structured")] if d.phase == 1 else d.units
        cands = self._candidates(d, units)
        self._apply(d, cands)
        if self.fail_after_stage8 == d.doc_key:
            self.fail_after_stage8 = None
            raise RuntimeError(f"injected failure after stage 8 for {d.doc_key}")
        # Step 9, order-free: evidence liveness for this document is a function of its LATEST revision
        # only (A59): a span's evidence is live while the latest revision contains the span, or when the
        # latest states a different value in the same chain (replaced, kept for history); otherwise it
        # is removed. Re-synced on every arrival, so arrival order can't change the live set (I4).
        self._sync_closures(d.doc_key, now)
        if stage == "prose" or d.phase == 2:
            store.set_source(g, sid, {"ingested_at": self.clock()})       # step 10: completion marker

    # -- step 2-5 ---------------------------------------------------------------------------
    def _span_records(self, d: SourceDoc) -> list[dict]:
        occ: dict[str, int] = defaultdict(int)
        out = []
        slugs = [a for e in self.entities.values() for a in e["aliases"] if "-" in a and not a[0].isdigit()]
        for i, u in enumerate(d.units):
            n = ids.norm(u.text)
            sid = ids.span_id(d.doc_key, u.text, occ[n])
            occ[n] += 1
            u.span_id = sid  # type: ignore[attr-defined]
            role = "human"
            out.append({"id": sid, "doc_key": d.doc_key, "text": u.text,
                        "keys": ids.identifier_keys(u.text, slugs), "ts": u.ts,
                        "author_id": u.author_id or "", "author_role": role, "kind": d.kind,
                        "embed_model": providers.embed_model_name(), "char_start": u.char_start,
                        "char_end": u.char_end, "ordinal": i, "heading_path": u.heading_path,
                        "url": u.url or d.uri})
        return out

    def _spans(self, d: SourceDoc, latest: bool, prev_latest: str | None) -> None:
        g = self.g
        spans = self._span_records(d)
        existing = store.existing_spans(g, [s["id"] for s in spans])
        new = [s for s in spans if s["id"] not in existing]
        if new:
            vecs = providers.embed([s["text"] for s in new])
            for s, v in zip(new, vecs):
                s["embedding"] = v
        if prev_latest:
            store.close_has_span(g, prev_latest, self.clock())
        store.upsert_spans(g, d.source_id, spans, latest=latest, now=self.clock())
        if latest:
            store.set_next_chain(g, d.doc_key, [s["id"] for s in spans])
        mentions, authored = [], []
        for u in d.units:
            for m in self.index.find(u.text) if self.index else []:
                mentions.append({"span_id": u.span_id, "entity_id": m.entity_id, "start": m.start, "end": m.end,
                                 "method": m.method, "hedged": False})
            if u.author_id and u.author_id.startswith("person:") and u.author_id in self.entities:
                authored.append({"span_id": u.span_id, "person_id": u.author_id})
        store.add_mentions(g, mentions)
        store.add_authored_by(g, authored)
        if d.ticket_id:
            store.add_has_source(g, d.ticket_id, d.source_id)
        if d.decision_id:
            for u in d.units:
                if u.section in ("context", "decision"):
                    store.add_motivated_by(g, d.decision_id, u.span_id, u.section, self.clock())

    # -- step 6-7 ---------------------------------------------------------------------------
    def _candidates(self, d: SourceDoc, units: list[Unit]) -> list[tuple[Candidate, str]]:
        if not hasattr(d.units[0] if d.units else None, "span_id"):
            self._span_records(d)
        if d.source_id in self.screened:
            store.set_source(self.g, d.source_id, {"screen": "injection"})
            return []
        out: list[tuple[Candidate, str]] = []
        types = {k: registry.label_of(k) for k in self.entities}
        names = {k: v["name"] for k, v in self.entities.items()}
        prose_units = []
        for u in units:
            if u.structured:
                for f in u.structured:
                    out.append((Candidate(
                        f.predicate, f.subject_id, f.object_id, f.object_value, f.qualifier, f.negated,
                        f.valid_from, f.basis, u.span_id, 0, len(u.text), d.source_id, "structured", 1.0,
                        f"structured:{d.kind}"), u.text))
                continue
            if not u.prose:
                continue
            ments = self.index.find(u.text) if self.index else []
            if ments:
                prose_units.append((u, ments))
        # LLM extraction is I/O-bound (6–11 s per call on free-tier models): run the spans of one Source
        # concurrently, keeping unit order so the report and candidate order stay deterministic.
        with ThreadPoolExecutor(max_workers=EXTRACT_WORKERS) as pool:
            extracted = list(pool.map(lambda um: extract(um[0].text, "", um[1], types, names, self.live), prose_units))
        for (u, ments), xs in zip(prose_units, extracted):
            form = "chat" if d.kind in ("chat", "chat_session") else "prose"
            for x in xs:
                if x.hedged:
                    self.report.add(source=d.source_id, span=u.span_id, outcome="hedged",
                                    candidate=f"{x.predicate}({x.subject_id},{x.object_id or x.object_value})")
                    self.g.write("MATCH (s:Span {id:$s})-[m:MENTIONS]->(e:Entity) WHERE e.id IN $e "
                                 "SET m.hedged = true", {"s": u.span_id, "e": [x.subject_id, x.object_id]},
                                 template="hedge")
                    continue
                vf, basis = (iso_ms(x.stated_date), "stated") if x.stated_date else (u.ts, "source_time")
                out.append((Candidate(x.predicate, x.subject_id, x.object_id, x.object_value, x.qualifier,
                                      x.negated, vf, basis, u.span_id, x.quote_start, x.quote_end, d.source_id,
                                      form, x.confidence, extractor_name(self.live)), u.text))
        return out

    # -- step 8 -----------------------------------------------------------------------------
    def _apply(self, d: SourceDoc, cands: list[tuple[Candidate, str]]) -> None:
        wp = WritePath(self.g, self.clock, {k: v["name"] for k, v in self.entities.items()})
        by_chain: dict[str, list[Candidate]] = defaultdict(list)
        for c, text in cands:
            try:
                validate(self.g, c, self.entities, text)
                if c.subject_id not in self.entities or (c.object_id and c.object_id not in self.entities):
                    raise ValidationError("unknown entity")
            except (ValidationError, KeyError) as e:
                self.report.add(source=d.source_id, span=c.span_id, outcome=f"rejected({e})",
                                candidate=_cstr(c))
                continue
            by_chain[c.chain_id].append(c)
        for chain, cs in by_chain.items():
            for attempt in range(4):
                try:
                    plan = wp.new_plan()
                    for c in cs:
                        wp.add_candidate(plan, c)
                    res = wp.execute(plan)
                    break
                except Exception:  # noqa: BLE001 - version conflict: re-read and retry (02 §4)
                    if attempt == 3:
                        raise
                    time.sleep(0.01)
            status = {}
            for snap in plan.chains.values():
                for u in plan.updates:
                    status[u["id"]] = u["status"]
            for o in res["outcomes"]:
                st = status.get(o["assertion_id"], "")
                self.report.add(source=d.source_id, span=o["candidate"].span_id, chain=chain,
                                candidate=_cstr(o["candidate"]),
                                outcome=o["outcome"] if o["outcome"].startswith("dedup") else (st or "written"),
                                assertion_id=o["assertion_id"])

    # -- step 9 -----------------------------------------------------------------------------
    def _sync_closures(self, doc_key: str, now: int) -> None:
        g = self.g
        latest = next((r["id"] for r in store.revisions(g, doc_key) if r["is_latest"]), None)
        if not latest:
            return
        # chains the latest revision states, through the spans it contains (shared spans included)
        stated: dict[str, set[str]] = defaultdict(set)
        for r in g.q("stated_by_latest", {"s": latest}):
            stated[r["chain"]].add(r["aid"])
        rows = g.q("doc_evidence", {"k": doc_key}, timeout=10000)
        latest_spans = {r["id"] for r in g.q("latest_spans", {"l": latest})}
        reopen, replace, remove = [], [], []
        for r in rows:
            if r["span"] in latest_spans:
                if r["rm"] != MAX or r["rb"]:
                    reopen.append({"aid": r["aid"], "span": r["span"]})
            elif stated.get(r["chain"]) and r["aid"] not in stated[r["chain"]]:
                if r["rm"] != MAX or r["rb"] != latest:
                    replace.append({"aid": r["aid"], "span": r["span"]})
            elif r["rm"] == MAX:
                remove.append({"aid": r["aid"], "span": r["span"]})
        if reopen:
            g.write("UNWIND $x AS x MATCH (a:Assertion {id:x.aid})-[e:EVIDENCED_BY]->(:Span {id:x.span}) "
                    "SET e.removed_at = $max, e.replaced_by = ''", {"x": reopen, "max": MAX}, template="sync_reopen")
        if replace:
            g.write("UNWIND $x AS x MATCH (a:Assertion {id:x.aid})-[e:EVIDENCED_BY]->(:Span {id:x.span}) "
                    "SET e.removed_at = $max, e.replaced_by = $l", {"x": replace, "max": MAX, "l": latest},
                    template="sync_replace")
        if remove:
            g.write("UNWIND $x AS x MATCH (a:Assertion {id:x.aid})-[e:EVIDENCED_BY]->(:Span {id:x.span}) "
                    "SET e.removed_at = $now", {"x": remove, "now": now}, template="sync_remove")
        for lst, outcome in ((replace, "replaced"), (remove, "removed"), (reopen, "reopened")):
            for x in lst:
                self.report.add(source=latest, span=x["span"], outcome=outcome, assertion_id=x["aid"])
        # authority depends on live evidence: recompute the touched chains (no retraction yet)
        changed = {x["aid"] for x in reopen + replace + remove}
        touched = sorted({r["chain"] for r in rows if r["aid"] in changed})
        if touched:
            self._recompute(touched)

    def _recompute(self, chains: list[str]) -> None:
        wp = WritePath(self.g, self.clock, {k: v["name"] for k, v in self.entities.items()})
        for c in chains:
            row = self.g.q("chain_meta", {"c": c})
            if not row:
                continue
            plan = wp.new_plan()
            plan.chains[c] = __import__("brain.write_path", fromlist=["load_chain"]).load_chain(
                self.g, c, row[0]["p"], row[0]["q"] or "", row[0]["k"])
            wp.execute(plan)

    def _retract_unsupported(self) -> None:
        """End of a run: an assertion with no live evidence of rank >= 1 and no proposal provenance is
        retracted (A14a). Deferred to the end so closures can be re-synced freely during the run."""
        rows = self.g.q("unsupported", {"max": MAX}, timeout=10000)
        if not rows:
            return
        wp = WritePath(self.g, self.clock, {k: v["name"] for k, v in self.entities.items()})
        plan = wp.new_plan()
        for r in rows:
            wp.load_for_assertion(plan, r["aid"])
            wp.retract(plan, r["aid"])
            self.report.add(source="", span="", outcome="retracted", assertion_id=r["aid"])
        wp.execute(plan)


def _safe_extract(text, ments, types, names, live=False):
    try:
        return extract(text, "", ments, types, names, live)
    except Exception:  # noqa: BLE001 - the per-Source pass will retry or fall back
        return None


def _cstr(c: Candidate) -> str:
    neg = "¬" if c.negated else ""
    return f"{neg}{c.predicate}{'+' + c.qualifier if c.qualifier else ''}({c.subject_id},{c.object_id or '=' + c.object_value})@{c.valid_from}/{c.form}"
