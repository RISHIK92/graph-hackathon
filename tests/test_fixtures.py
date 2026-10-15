"""08 named fixtures not covered elsewhere, each asserted against its hand-written expected result.

Covered here: FX-R1-S1 (+ revision variant), S5, S6, S7, S8, S9, S12, S13; FX-R2-S1b, S4, S5, S5b, S6, S8, S9.
Every expected value below is copied from docs/spec/08-fixtures.md, never from an engine.
"""
from __future__ import annotations

import pytest

from brain import ids, schema, store
from brain.actions import Actions, Actor, Refused
from brain.config import MAX
from brain.db import Graph
from brain.tools import Ctx, run_tool
from brain.chain import past_belief
from brain.write_path import Candidate, WritePath, load_chain
from ingest.connectors import SourceDoc, StructuredFact, Unit, _paragraph_units
from ingest.pipeline import Ingestor

from .conftest import Clock, make_span, seed_basic
from .test_actions import _fact, actor, status_of, world  # noqa: F401

LEDGER = "system:ledger"
A, B = "team:infra", "team:payments"          # A < B by value id (08 conventions); I < P likewise
P, I = "team:payments", "team:infra"


# helpers

def fresh_like(g: Graph) -> Graph:
    import uuid
    h = Graph(name=f"fx_{uuid.uuid4().hex[:8]}", port=g.port)
    schema.create(h)
    return h


def wiki_doc(doc_key: str, updated_at: int, text: str) -> SourceDoc:
    d = SourceDoc(doc_key, "wiki", "confluence", doc_key.rsplit(":", 1)[-1], doc_key, "", updated_at, updated_at,
                  "", text)
    d.units = _paragraph_units(text, updated_at)
    return d


def catalog_doc(doc_key: str, updated_at: int, owner: str, owner_from: int) -> SourceDoc:
    text = f"systems:\n- id: {LEDGER}\n  owner: {owner}\n  owner_from: {owner_from}\n"
    d = SourceDoc(doc_key, "catalog", "backstage", "services", "Catalog", "", updated_at, updated_at, "", text)
    d.units = [Unit(text, 0, len(text), updated_at, "systems",
                    structured=[StructuredFact("OWNS", owner, LEDGER, valid_from=owner_from)], prose=False, phase=1)]
    return d


def chat_doc(doc_key: str, ts: int, text: str) -> SourceDoc:
    d = SourceDoc(doc_key, "chat", "slack", doc_key.rsplit("/", 1)[-1], "", "", ts, ts, "", text)
    d.units = [Unit(text, 0, len(text), ts, "eng")]
    return d


def tuples(g: Graph) -> list[tuple]:
    rows = g.ro("MATCH (a:Assertion) WHERE a.retracted_at = $max "
                "OPTIONAL MATCH (a)-[e:EVIDENCED_BY]->(s:Span) WHERE e.removed_at = $max "
                "WITH a, collect(DISTINCT s.id) AS ev "
                "RETURN a.chain_id AS c, a.subject_id AS s, a.valid_from AS vf, a.valid_to AS vt, a.status AS st, ev",
                {"max": MAX})
    return sorted((r["c"], r["s"], r["vf"], r["vt"], r["st"], tuple(sorted(r["ev"]))) for r in rows)


def sources(g: Graph) -> list[tuple]:
    return sorted((r["id"], r["latest"]) for r in g.ro("MATCH (s:Source) RETURN s.id AS id, s.is_latest AS latest"))


def span_ts(g: Graph) -> list[tuple]:
    return sorted((r["id"], r["ts"]) for r in g.ro("MATCH (s:Span) RETURN s.id AS id, s.ts AS ts"))


def owns_rows(g: Graph) -> dict[str, dict]:
    rows = g.ro("MATCH (a:Assertion {predicate:'OWNS', object_id:$l}) RETURN a.id AS id, a.subject_id AS s, "
                "a.valid_from AS vf, a.valid_to AS vt, a.status AS st", {"l": LEDGER})
    return {r["s"]: r for r in rows}


def evidence_edges(g: Graph, aid: str) -> list[dict]:
    return g.ro("MATCH (a:Assertion {id:$id})-[e:EVIDENCED_BY]->(s:Span) RETURN s.id AS span, e.removed_at AS rm, "
                "e.replaced_by AS rb, e.recorded_at AS ra, e.form AS form, e.action_id AS act ORDER BY ra", {"id": aid})


def history_facts(g: Graph, now: int, entity: str, pred: str, T: int | None = None, V: int | None = None) -> dict:
    pack = run_tool(Ctx(g, now=now, belief_at=T, as_of=V), "get_history", {"entity_id": entity, "predicate": pred})
    return {f["assertion_id"]: f for it in pack["items"] for f in it["facts"]}


def pack_spans(pack: dict) -> dict[str, dict]:
    return {s["span_id"]: s for it in pack["items"] for s in it["spans"]}


def versions(g: Graph) -> dict:
    return {r["id"]: r["v"] for r in g.ro("MATCH (c:Chain) RETURN c.id AS id, c.version AS v")}


# FX-R1-S1

def test_fx_r1_s1_catalog_then_chat_every_order(g):
    """A (catalogue, rank 4, v10) current; B (chat, rank 1, v20) disputed, in A's open_disputes; I4."""
    cat = catalog_doc("catalog:backstage:services", 5, A, 10)
    chat = chat_doc("chat:slack:eng/20", 20, "Payments owns Ledger.")
    results = []
    for order_seed in (None, 1, 2):
        h = g if order_seed is None else fresh_like(g)
        try:
            seed_basic(h)
            Ingestor(h, Clock(100)).ingest_docs([chat, cat], seed=order_seed)
            rows = owns_rows(h)
            assert rows[A]["st"] == "current" and rows[A]["vf"] == 10 and rows[A]["vt"] == MAX
            assert rows[B]["st"] == "disputed"
            pack = run_tool(Ctx(h, now=200), "get_owner", {"entity_id": LEDGER})
            owns = [f for f in pack["items"][0]["facts"] if f["predicate"] == "OWNS"][0]
            assert owns["subject_id"] == A and owns["open_disputes"] == [rows[B]["id"]]
            results.append((tuples(h), sources(h)))
        finally:
            if h is not g:
                h.delete()
    assert results[0] == results[1] == results[2]


def test_fx_r1_s1_revision_variant_unchanged_span_no_new_edge(g):
    """Two catalogue revisions (updated_at 5 and 9) stating A from v10 unchanged, shuffled: the revision
    with updated_at 9 is latest in both orders, the unchanged span gets no new evidence edge (A56),
    and Source IDs are the same in both orders."""
    r5 = catalog_doc("catalog:backstage:services", 5, A, 10)
    r9 = catalog_doc("catalog:backstage:services", 9, A, 10)
    assert r5.source_id != r9.source_id
    outs = []
    for order in ([r5, r9], [r9, r5]):
        h = fresh_like(g)
        try:
            seed_basic(h)
            ing = Ingestor(h, Clock(100))
            for d in order:                    # one arrival at a time, in the given order
                ing.ingest_docs([d])
            latest = [s for s, l in sources(h) if l]
            assert latest == [r9.source_id]
            rows = owns_rows(h)
            assert rows[A]["st"] == "current" and rows[A]["vf"] == 10
            ev = evidence_edges(h, rows[A]["id"])
            assert len(ev) == 1 and ev[0]["rm"] == MAX and not ev[0]["rb"]       # one edge, still live
            outs.append((tuples(h), sources(h), span_ts(h)))
        finally:
            h.delete()
    assert outs[0] == outs[1]


# FX-R1-S5: proposal confirmed, undone, confirmed again through separate clicks

def _run_s5(world):
    g, clock = world["g"], world["clock"]
    acts = Actions(g, clock)
    t0 = clock()
    R, C30, U40, C50 = t0 + 20, t0 + 30, t0 + 40, t0 + 50
    clock.t = R
    r = acts.route_to_owner(actor("person:eve"), ticket_id="ticket:rds-42")
    Pid = r["proposal"]
    clock.t = C30
    c1 = acts.confirm_fact(actor("person:priya"), action_id=r["action_id"])
    F30 = c1["produced"][0]
    clock.t = U40
    u = acts.undo_action(actor("person:priya"), c1["action_id"])
    clock.t = C50
    c2 = acts.confirm_fact(actor("person:priya"), action_id=r["action_id"])
    F50 = c2["produced"][0]
    # three distinct Action IDs, two distinct confirmation Sources = hash(action_id) (A60)
    assert len({c1["action_id"], u["action_id"], c2["action_id"]}) == 3
    assert c1["confirmation_source"] != c2["confirmation_source"]
    assert c1["confirmation_source"] == ids.confirmation_source_id(c1["action_id"])
    assert c2["confirmation_source"] == ids.confirmation_source_id(c2["action_id"])
    # F30 valid from v30, CONFIRMS P; F50 valid from v50 with a different ID; F30 stays retracted
    f30 = acts._assertion(F30)
    f50 = acts._assertion(F50)
    assert F30 != F50
    assert f30["valid_from"] == C30 and f30["status"] == "retracted" and f30["retracted_at"] == U40
    assert f50["valid_from"] == C50 and f50["status"] == "current"
    assert g.ro("MATCH (n:Assertion)-[:CONFIRMS]->(p:Assertion {id:$p}) RETURN collect(n.id) AS n", {"p": Pid})[0]["n"] \
        and set(g.ro("MATCH (n:Assertion)-[:CONFIRMS]->(p:Assertion {id:$p}) RETURN n.id AS n", {"p": Pid})[0].values()) <= {F30, F50}
    now = C50 + 10
    # T35 / V35: F30, and P shows confirmed
    h = history_facts(g, now, "ticket:rds-42", "ASSIGNED_TO", T=t0 + 35, V=t0 + 35)
    assert h[F30]["status"] == "current" and h[F30]["valid_from"] == C30
    assert h[Pid]["status"] == "proposed"
    assert F50 not in h
    # T45 / V45: the pre-confirm assignment (none), and P shows proposed
    h = history_facts(g, now, "ticket:rds-42", "ASSIGNED_TO", T=t0 + 45, V=t0 + 45)
    assert [a for a, f in h.items() if f["status"] == "current"] == []
    assert h[Pid]["status"] == "proposed"
    assert F30 not in h and F50 not in h
    # T55 / V55: F50; F30 stays retracted
    h = history_facts(g, now, "ticket:rds-42", "ASSIGNED_TO", T=t0 + 55, V=t0 + 55)
    assert h[F50]["status"] == "current" and h[F50]["valid_from"] == C50
    assert F30 not in h
    assert status_of(g, F30) == "retracted"
    return g, now, t0, Pid, F30, F50


def test_fx_r1_s5_confirm_undo_reconfirm_distinct_ids_and_past_reads(world):
    _run_s5(world)


def test_fx_r1_s5_proposal_shows_confirmed_then_proposed_then_confirmed(world):
    g, now, t0, Pid, F30, F50 = _run_s5(world)
    h = history_facts(g, now, "ticket:rds-42", "ASSIGNED_TO", T=t0 + 35, V=t0 + 35)
    assert h[Pid]["confirmed_by"] == {"assertion_id": F30}                           # P shows confirmed
    h = history_facts(g, now, "ticket:rds-42", "ASSIGNED_TO", T=t0 + 45, V=t0 + 45)
    assert "confirmed_by" not in h[Pid]                                                # P shows proposed
    h = history_facts(g, now, "ticket:rds-42", "ASSIGNED_TO", T=t0 + 55, V=t0 + 55)
    assert h[Pid]["confirmed_by"] == {"assertion_id": F50}                           # P shows confirmed


# FX-R1-S6: a later structured statement overrides a confirmation (L5)

def test_fx_r1_s6_structured_restatement_after_confirmation(world):
    g, clock, wp = world["g"], world["clock"], world["wp"]
    acts = Actions(g, clock)
    # S3 state: A = Payments from v2 (rank 4), B = Infra from v3 (rank 1), B confirmed at C
    Bid = _fact(wp, "OWNS", I, LEDGER, 3, "sp6", form="chat")
    clock.tick()
    acts.confirm_fact(actor("person:priya"), assertion_id=Bid)
    T35 = clock.tick()                       # a belief time after C and before r50
    clock.tick()
    make_span(g, "sp_r50", "catalog: payments owns ledger from 5", clock())
    A2 = _fact(wp, "OWNS", P, LEDGER, 5, "sp_r50", form="structured")
    r50 = g.ro("MATCH (a:Assertion {id:$id}) RETURN a.recorded_at AS r", {"id": A2})[0]["r"]
    now = clock.tick()
    # Now / V45: A from v40; B superseded [v20, v40)
    pack = run_tool(Ctx(g, now=now, as_of=6), "get_owner", {"entity_id": LEDGER})
    owns = [f for f in pack["items"][0]["facts"] if f["predicate"] == "OWNS"][0]
    assert owns["subject_id"] == P and owns["valid_from"] == 5 and owns["status"] == "current"
    b = acts._assertion(Bid)
    assert b["status"] == "superseded"
    assert g.ro("MATCH (a:Assertion {id:$id}) RETURN a.valid_from AS vf, a.valid_to AS vt", {"id": Bid})[0] == {"vf": 3, "vt": 5}
    # T35 / V45: B, and the pack contains no evidence recorded at r50 (A59)
    pack = run_tool(Ctx(g, now=now, belief_at=T35, as_of=6), "get_owner", {"entity_id": LEDGER})
    owns = [f for f in pack["items"][0]["facts"] if f["predicate"] == "OWNS"][0]
    assert owns["subject_id"] == I
    assert "sp_r50" not in pack_spans(pack)
    assert A2 not in {f["assertion_id"] for it in pack["items"] for f in it["facts"]}
    # Now / V35: B
    pack = run_tool(Ctx(g, now=now, as_of=4), "get_owner", {"entity_id": LEDGER})
    owns = [f for f in pack["items"][0]["facts"] if f["predicate"] == "OWNS"][0]
    assert owns["subject_id"] == I
    # flag_stale_docs labels the r50 span "overrides a confirmation" (L5)
    found = acts.stale_detection(LEDGER)
    assert [(f["span"], f["why"]) for f in found if f["why"] == "overrides a confirmation"] == [("sp_r50", "overrides a confirmation")]
    assert r50 > T35


# FX-R1-S7 / S8: revision change and removal; FX-R2-S1b / S8 in Ledger notation

def _two_revisions(g: Graph, texts: tuple[str, str], order: tuple[int, int] = (0, 1), clock: Clock | None = None):
    clock = clock or Clock(100)
    w1 = wiki_doc("wiki:confluence:ledger", 10, texts[0])
    w2 = wiki_doc("wiki:confluence:ledger", 20, texts[1])
    docs = [w1, w2]
    ing = Ingestor(g, clock)
    arrival = {}
    for i in order:
        ing.ingest_docs([docs[i]])
        arrival[docs[i].source_id] = clock()
        clock.tick(5)
    return w1, w2, arrival, clock


def test_fx_r1_s7_revision_replaces_paragraph(g):
    seed_basic(g)
    w1, w2, _, clock = _two_revisions(g, ("Infra owns Ledger.", "Payments owns Ledger."))
    rows = owns_rows(g)
    a, b = rows[A], rows[B]
    assert (a["st"], a["vf"], a["vt"]) == ("superseded", 10, 20)
    assert (b["st"], b["vf"], b["vt"]) == ("current", 20, MAX)
    ev = evidence_edges(g, a["id"])
    assert len(ev) == 1 and ev[0]["rm"] == MAX and ev[0]["rb"] == w2.source_id        # live, replaced_by = rev 2
    now = clock()
    pack = run_tool(Ctx(g, now=now), "get_history", {"entity_id": LEDGER, "predicate": "OWNS"})
    facts = {f["assertion_id"]: f for it in pack["items"] for f in it["facts"]}
    assert facts[a["id"]]["status"] == "superseded"
    sp = pack_spans(pack)[ev[0]["span"]]
    assert sp["live"] is False and a["id"] in sp["cites"]                            # greyed, still cited


def test_fx_r1_s8_revision_deletes_paragraph(g):
    seed_basic(g)
    w1, w2, arrival, clock = _two_revisions(g, ("Infra owns Ledger.", "Nothing about ownership here."))
    rows = owns_rows(g)
    a = rows[A]
    assert a["st"] == "retracted" and B not in rows
    ev = evidence_edges(g, a["id"])
    assert len(ev) == 1 and ev[0]["rm"] == arrival[w2.source_id]                     # removed_at = rev 2 arrival
    assert g.ro("MATCH ()-[o:OWNS]->(:System {id:$l}) WHERE o.valid_to = $m RETURN count(o) AS n",
                {"l": LEDGER, "m": MAX})[0]["n"] == 0                                   # no current owner
    now = clock()
    assert a["id"] not in history_facts(g, now, LEDGER, "OWNS")
    T = arrival[w1.source_id]                                                          # before revision 2
    past = run_tool(Ctx(g, now=now, belief_at=T, as_of=15), "get_owner", {"entity_id": LEDGER})
    owns = [f for f in past["items"][0]["facts"] if f["predicate"] == "OWNS"][0]
    assert owns["subject_id"] == A and owns["valid_from"] == 10
    assert ev[0]["span"] in pack_spans(past)


def test_fx_r2_s1b_both_orders_identical(g):
    outs = []
    for order in ((0, 1), (1, 0)):
        h = fresh_like(g)
        try:
            seed_basic(h)
            w1, w2, _, _ = _two_revisions(h, ("Payments owns Ledger.", "Infra owns Ledger."), order)
            assert [s for s, l in sources(h) if l] == [w2.source_id]
            rows = owns_rows(h)
            assert (rows[P]["st"], rows[P]["vf"], rows[P]["vt"]) == ("superseded", 10, 20)
            assert (rows[I]["st"], rows[I]["vf"], rows[I]["vt"]) == ("current", 20, MAX)
            ev = evidence_edges(h, rows[P]["id"])
            assert len(ev) == 1 and ev[0]["rm"] == MAX and ev[0]["rb"] == w2.source_id
            if order == (1, 0):   # W1 arrived late: its HAS_SPAN edges are closed, it removed nothing (A58)
                hs = h.ro("MATCH (:Source {id:$s})-[h:HAS_SPAN]->() RETURN h.removed_at AS rm", {"s": w1.source_id})
                assert hs and all(r["rm"] != MAX for r in hs)
                assert all(e["rm"] == MAX for e in evidence_edges(h, rows[I]["id"]))
            outs.append((tuples(h), sources(h), span_ts(h)))
        finally:
            h.delete()
    assert outs[0] == outs[1]


def test_fx_r2_s8_change_and_removal(g):
    seed_basic(g)
    w1, w2, arrival, clock = _two_revisions(g, ("Payments owns Ledger.", "Infra owns Ledger."))
    now = clock()
    pack = run_tool(Ctx(g, now=now, as_of=12), "get_owner", {"entity_id": LEDGER})      # who owned Ledger at t2?
    owns = [f for f in pack["items"][0]["facts"] if f["predicate"] == "OWNS"][0]
    assert owns["subject_id"] == P and owns["status"] == "superseded"
    rows = owns_rows(g)
    ev = evidence_edges(g, rows[P]["id"])
    assert ev[0]["rb"] == w2.source_id and ev[0]["rm"] == MAX
    assert rows[P]["id"] in pack_spans(pack)[ev[0]["span"]]["cites"]
    assert (rows[I]["st"], rows[I]["vf"]) == ("current", 20)
    # removal variant
    h = fresh_like(g)
    try:
        seed_basic(h)
        w1, w2, arrival, clock = _two_revisions(h, ("Payments owns Ledger.", "The page says nothing now."))
        rows = owns_rows(h)
        assert rows[P]["st"] == "retracted" and I not in rows
        assert h.ro("MATCH ()-[o:OWNS]->(:System {id:$l}) WHERE o.valid_to = $m RETURN count(o) AS n",
                    {"l": LEDGER, "m": MAX})[0]["n"] == 0
        past = run_tool(Ctx(h, now=clock(), belief_at=arrival[w1.source_id], as_of=12), "get_owner",
                        {"entity_id": LEDGER})
        assert [f["subject_id"] for f in past["items"][0]["facts"] if f["predicate"] == "OWNS"] == [P]
    finally:
        h.delete()


# FX-R1-S9: ADR draft → confirm → undo draft

def _trace_statuses(g: Graph, now: int, T: int, V: int, entity: str) -> tuple[dict, dict]:
    pack = run_tool(Ctx(g, now=now, belief_at=T, as_of=V), "trace_decision", {"entity_id": entity})
    facts = {f["assertion_id"]: f for it in pack["items"] for f in it["facts"]}
    return facts, pack


def _run_s9(world):
    g, clock, wp = world["g"], world["clock"], world["wp"]
    OLD, S, X = "decision:adr-001", LEDGER, "person:priya"
    old_acc = _fact(wp, "HAS_STATUS", OLD, "", 10, "sp7", value="accepted")
    _fact(wp, "AFFECTS", OLD, S, 10, "sp7")
    _fact(wp, "DECIDED_BY", OLD, X, 10, "sp7")
    acts = Actions(g, clock)
    t0 = clock()
    clock.t = t0 + 20
    d = acts.draft_adr_supersession(actor("person:eve"), OLD, "move to Aurora")
    NEW = d["decision"]
    props = d["proposals"]
    assert len(props) == 4                                             # accepted, superseded, REPLACES, AFFECTS
    assert g.ro("MATCH (:Decision {id:$n})-[m:MOTIVATED_BY]->(s:Span) RETURN collect(s.kind) AS k", {"n": NEW})[0]["k"] == ["wiki"]
    clock.t = t0 + 30
    c = acts.confirm_fact(actor(X), action_id=d["action_id"])
    C30 = clock()
    clock.t = t0 + 40
    acts.undo_action(actor("person:eve"), d["action_id"])
    now = t0 + 50
    V = t0 + 35

    def chains_at(T):
        out = {}
        for ent, pred in ((OLD, "HAS_STATUS"), (NEW, "HAS_STATUS"), (NEW, "REPLACES"), (NEW, "AFFECTS"), (NEW, "DECIDED_BY")):
            out.update(history_facts(g, now, ent, pred, T=T, V=V))
        return out

    def current(facts):
        return {(f["predicate"], f["subject_id"], f["object_id"] or f["object_value"]): f
                for f in facts.values() if f["status"] == "current"}

    # T25 / V35: only the old ADR is accepted; the proposals are pending
    facts = chains_at(t0 + 25)
    assert facts[old_acc]["status"] == "current"
    assert set(current(facts)) == {("HAS_STATUS", OLD, "accepted")}
    for p in props:
        assert facts[p]["status"] == "proposed", p
    # T35 and T45 / V35: new accepted from v30, old superseded from v30, REPLACES, AFFECTS(new,S), DECIDED_BY(new,X)
    for T, shown in ((t0 + 35, "confirmed"), (t0 + 45, "withdrawn")):
        facts = chains_at(T)
        k = current(facts)
        assert k[("HAS_STATUS", NEW, "accepted")]["valid_from"] == C30
        assert k[("HAS_STATUS", OLD, "superseded")]["valid_from"] == C30
        assert facts[old_acc]["status"] == "superseded" and facts[old_acc]["valid_to"] == C30
        assert ("REPLACES", NEW, OLD) in k and ("AFFECTS", NEW, S) in k and ("DECIDED_BY", NEW, X) in k
        # trace_decision(S) returns the new ADR, with its proposals (proposed at T35, withdrawn at T45) and the Action
        tfacts, pack = _trace_statuses(g, now, T, V, S)
        assert any(it["path"] and it["path"]["steps"][0]["node"]["id"] == NEW for it in pack["items"])
        assert ("HAS_STATUS", NEW, "accepted") in current(tfacts)
        for p in props:
            assert tfacts[p]["status"] == ("proposed" if shown == "confirmed" else "retracted")
        acts_in = {a["action_id"]: a for it in pack["items"] for a in it.get("actions") or []}
        assert acts_in[d["action_id"]]["status"] == "undone"                       # the draft Action stays readable
    # the draft text is viewable and marked withdrawn
    src = g.ro("MATCH (:Action {id:$a})-[:PRODUCED]->(s:Source {kind:'draft'})-[:HAS_SPAN]->(sp:Span) "
               "RETURN s.status AS st, collect(sp.text) AS texts", {"a": d["action_id"]})[0]
    assert src["st"] == "deleted" and any("replaces" in t for t in src["texts"])
    # literal HAS_STATUS rows from the Python engine (no OBJECT match)
    snap = load_chain(g, "ch_HAS_STATUS:" + NEW, "HAS_STATUS", "", NEW)
    r = past_belief(snap.records, t0 + 45, V)
    assert r["value"] == "=accepted" and r["valid_from"] == C30
    assert g.ro("MATCH (a:Assertion {id:$id})-[:OBJECT]->() RETURN count(*) AS n", {"id": r["run"][0]})[0]["n"] == 0
    return g, now, t0, V, S, props, c


def test_fx_r1_s9_adr_draft_confirm_undo_draft(world):
    _run_s9(world)


def test_fx_r1_s9_proposals_pending_at_t25_confirmed_at_t35(world):
    g, now, t0, V, S, props, c = _run_s9(world)
    facts, _ = _trace_statuses(g, now, t0 + 25, V, S)
    assert all("confirmed_by" not in facts[p] for p in props)                          # pending
    facts, _ = _trace_statuses(g, now, t0 + 35, V, S)
    assert all(facts[p]["confirmed_by"]["assertion_id"] in c["produced"] for p in props)   # confirmed (A55)


# FX-R1-S12: a component change closes ABOUT with a negative (A65) and moves ticket_leads

def test_fx_r1_s12_negative_about_and_ticket_leads(world):
    g, clock, wp = world["g"], world["clock"], world["wp"]
    K, SA, SB = "ticket:rds-42", LEDGER, "system:billing"
    store.upsert_entities(g, [{"id": SB, "name": "Billing", "aliases": []}])
    make_span(g, "sp_b", "infra owns billing", 1)
    make_span(g, "sp_k20", "rds-42 component: billing (was ledger)", 20)
    _fact(wp, "OWNS", I, SB, 1, "sp_b")
    about_a = world["ids"]["about"]                                    # ABOUT(K, A) + from v1 (fixture's v10)
    plan = wp.new_plan()
    neg = wp.add_candidate(plan, Candidate("ABOUT", K, SA, negated=True, valid_from=20, span_id="sp_k20",
                                           quote_end=5, form="structured", source_id="src:test"))["assertion_id"]
    pos = wp.add_candidate(plan, Candidate("ABOUT", K, SB, valid_from=20, span_id="sp_k20", quote_end=5,
                                           form="structured", source_id="src:test"))["assertion_id"]
    wp.execute(plan)
    rows = {r["id"]: r for r in g.ro("MATCH (a:Assertion {predicate:'ABOUT', subject_id:$k}) RETURN a.id AS id, "
                                     "a.object_id AS o, a.negated AS n, a.valid_from AS vf, a.valid_to AS vt, "
                                     "a.status AS st", {"k": K})}
    assert (rows[about_a]["st"], rows[about_a]["vf"], rows[about_a]["vt"]) == ("superseded", 1, 20)
    assert rows[neg]["n"] is True and rows[neg]["st"] == "current" and rows[neg]["vf"] == 20
    assert rows[pos]["st"] == "current" and rows[pos]["vf"] == 20 and rows[pos]["o"] == SB
    edges = g.ro("MATCH (:Ticket {id:$k})-[r:ABOUT]->(x) RETURN x.id AS x, r.valid_from AS vf, r.valid_to AS vt ORDER BY vf",
                 {"k": K})
    assert edges == [{"x": SA, "vf": 1, "vt": 20}, {"x": SB, "vf": 20, "vt": MAX}]
    acts = Actions(g, clock)
    clock.tick()
    r = acts.route_to_owner(actor("person:eve"), ticket_id=K)
    assert r["target"] == "person:bob"                                  # Lb
    clock.tick()
    with pytest.raises(Refused) as e:                                   # La's confirm on K is refused, naming Lb
        acts.confirm_fact(actor("person:priya"), action_id=r["action_id"])
    assert [x["person_id"] for x in e.value.eligible] == ["person:bob"]
    assert e.value.eligible[0]["path"] == "rds-42 −ABOUT→ billing infra −OWNS→ billing bob −LEADS→ infra"


# FX-R1-S13: proposal collision on the same day

def test_fx_r1_s13_collision_refused(world):
    g, clock, wp = world["g"], world["clock"], world["wp"]
    acts = Actions(g, clock)
    r = acts.route_to_owner(actor("person:eve"), ticket_id="ticket:rds-42")      # P: RDS-42 → Priya
    make_span(g, "sp_f", "rds-42 assignee priya", clock())
    F = _fact(wp, "ASSIGNED_TO", "ticket:rds-42", "person:priya", clock(), "sp_f")   # structured F, same day
    assert status_of(g, F) == "current"
    vers = versions(g)
    n_assert = g.ro("MATCH (a:Assertion) RETURN count(a) AS n")[0]["n"]
    with pytest.raises(Refused) as e:
        acts.confirm_fact(actor("person:priya"), action_id=r["action_id"])
    assert e.value.reason == f"collides with fact {F}; confirm {F} instead"
    assert versions(g) == vers
    assert g.ro("MATCH (a:Assertion) RETURN count(a) AS n")[0]["n"] == n_assert
    ref = g.ro("MATCH (ac:Action {status:'refused'}) RETURN ac.kind AS k, ac.summary AS s")
    assert ref == [{"k": "confirm_fact", "s": e.value.reason}]
    assert e.value.action_id and status_of(g, r["proposal"]) == "proposed"


# FX-R2-S4: re-confirm after a dispute reopens

def test_fx_r2_s4_second_confirmation_admitted_after_reopen(world):
    g, clock, wp = world["g"], world["clock"], world["wp"]
    acts = Actions(g, clock)
    Pid = world["ids"]["own_p"]
    Iid = _fact(wp, "OWNS", I, LEDGER, 3, "sp6", form="chat")
    clock.tick()
    c1 = acts.confirm_fact(actor("person:priya"), assertion_id=Pid)
    C = clock()
    assert acts._open_disputes(acts._assertion(Pid), C) == []                       # I settled
    make_span(g, "sp_chat2", "Infra", C + 1, kind="chat")
    clock.tick(2)
    plan = wp.new_plan()
    out = wp.add_candidate(plan, Candidate("OWNS", I, LEDGER, valid_from=3, valid_from_basis="stated",
                                           span_id="sp_chat2", quote_end=5, form="chat", source_id="src:test"))
    wp.execute(plan)
    assert out == {"outcome": "dedup", "assertion_id": Iid}                           # same I, evidence authored after C
    assert acts._open_disputes(acts._assertion(Pid), clock()) == [Iid]                # open again
    clock.tick()
    c2 = acts.confirm_fact(actor("person:priya"), assertion_id=Pid)                   # admitted (A52)
    assert c2["action_id"] != c1["action_id"]
    assert acts._open_disputes(acts._assertion(Pid), clock()) == []                   # settled again
    conf = [e for e in evidence_edges(g, Pid) if e["form"] == "confirmation" and e["rm"] == MAX]
    assert len(conf) == 2                                                              # two live confirmation edges on P
    assert status_of(g, Pid) == "current" and status_of(g, Iid) == "disputed"


# FX-R2-S5: confirm, undo, confirm on a disputed and on a proposed target

def test_fx_r2_s5_repeat_confirmations_are_new_events(world):
    g, clock, wp = world["g"], world["clock"], world["wp"]
    acts = Actions(g, clock)
    Pid = world["ids"]["own_p"]
    Iid = _fact(wp, "OWNS", I, LEDGER, 3, "sp6", form="chat")
    before = tuples(g)
    clock.tick()
    c1 = acts.confirm_fact(actor("person:priya"), assertion_id=Iid)
    clock.tick()
    U = clock()
    acts.undo_action(actor("person:priya"), c1["action_id"])
    assert tuples(g) == before                                                         # I8
    clock.tick()
    c2 = acts.confirm_fact(actor("person:priya"), assertion_id=Iid)
    assert c1["confirmation_source"] != c2["confirmation_source"] and c1["action_id"] != c2["action_id"]
    conf = [e for e in evidence_edges(g, Iid) if e["form"] == "confirmation"]
    e1 = next(e for e in conf if e["act"] == c1["action_id"])
    e2 = next(e for e in conf if e["act"] == c2["action_id"])
    assert e1["rm"] == U and e2["rm"] == MAX
    assert status_of(g, Iid) == "current" and status_of(g, Pid) == "superseded"
    # proposed target
    clock.tick()
    r = acts.route_to_owner(actor("person:eve"), ticket_id="ticket:rds-42")
    clock.tick()
    n1 = acts.confirm_fact(actor("person:bob"), action_id=r["action_id"])["produced"][0]   # Infra now holds Ledger
    clock.tick()
    acts.undo_action(actor("person:bob"), next(a["id"] for a in g.ro(
        "MATCH (ac:Action)-[:PRODUCED]->(:Assertion {id:$n}) RETURN ac.id AS id", {"n": n1})))
    clock.tick()
    n2 = acts.confirm_fact(actor("person:bob"), action_id=r["action_id"])["produced"][0]
    assert n1 != n2 and status_of(g, n1) == "retracted" and status_of(g, n2) == "current"


# FX-R2-S5b: revert, restatement after retraction, repeated confirmation

def test_fx_r2_s5b_revert_and_restatement_generation(g):
    seed_basic(g)
    clock = Clock(100)
    ing = Ingestor(g, clock)
    revs = [wiki_doc("wiki:confluence:ledger", t, txt) for t, txt in
            ((10, "Payments owns Ledger."), (20, "Infra owns Ledger."), (30, "Payments owns Ledger."))]
    for d in revs:
        ing.ingest_docs([d])
        clock.tick(5)
    assert len({d.source_id for d in revs}) == 3                                       # updated_at is in the ID
    assert len(sources(g)) == 3
    # a retracted assertion restated later: new assertion, generation 1; the old keeps its retracted_at
    store.upsert_entities(g, [{"id": "system:billing", "name": "Billing", "aliases": []}])
    make_span(g, "s_a", "Payments owns Billing (stated 2025-01-01)", clock())
    wp = WritePath(g, clock)
    a0 = _fact(wp, "OWNS", P, "system:billing", 40, "s_a", form="prose")
    clock.tick()
    plan = wp.new_plan()
    wp.remove_evidence(plan, a0, span_id="s_a")
    wp.execute(plan)
    T_gap = clock()
    assert status_of(g, a0) == "retracted"
    clock.tick()
    make_span(g, "s_b", "Payments owns Billing (restated)", clock())
    a1 = _fact(wp, "OWNS", P, "system:billing", 40, "s_b", form="prose")
    rows = {r["id"]: r for r in g.ro("MATCH (a:Assertion) WHERE a.id IN $ids RETURN a.id AS id, a.generation AS gen, "
                                     "a.retracted_at AS rt, a.status AS st", {"ids": [a0, a1]})}
    assert a1 != a0 and rows[a1]["gen"] == 1 and rows[a1]["st"] == "current"
    assert rows[a0]["gen"] == 0 and rows[a0]["rt"] == T_gap
    snap = load_chain(g, "ch_OWNS:system:billing", "OWNS", "", "system:billing")
    assert past_belief(snap.records, T_gap, 45) is None or past_belief(snap.records, T_gap, 45)["value"] != P
    assert past_belief(snap.records, clock(), 45)["value"] == P
    # a repeated confirmation is a new Source
    make_span(g, "s_lead", "priya leads payments", 1)
    make_span(g, "s_ch", "infra owns ledger", 41)
    _fact(wp, "LEADS", "person:priya", P, 1, "s_lead")
    ch = _fact(wp, "OWNS", I, "system:ledger", 41, "s_ch", form="chat")
    acts = Actions(g, clock)
    clock.tick()
    c1 = acts.confirm_fact(actor("person:priya"), assertion_id=ch)
    clock.tick()
    acts.undo_action(actor("person:priya"), c1["action_id"])
    clock.tick()
    c2 = acts.confirm_fact(actor("person:priya"), assertion_id=ch)
    assert c1["confirmation_source"] != c2["confirmation_source"]
    assert g.ro("MATCH (s:Source {kind:'confirmation'}) RETURN count(s) AS n")[0]["n"] == 2


# FX-R2-S6: roster re-export, unchanged row vs changed row

def _s3_state(g: Graph, clock: Clock) -> tuple[Ingestor, str, str, Actions]:
    """I confirmed from t3 by Priya; P (catalogue, t2) superseded. The P row comes from an ingested catalogue."""
    seed_basic(g)
    make_span(g, "s_lead_p", "priya leads payments", 1)
    make_span(g, "s_lead_i", "bob leads infra", 1)
    wp = WritePath(g, clock)
    _fact(wp, "LEADS", "person:priya", P, 1, "s_lead_p")
    _fact(wp, "LEADS", "person:bob", I, 1, "s_lead_i")
    ing = Ingestor(g, clock)
    ing.ingest_docs([catalog_doc("catalog:backstage:services", 2, P, 2)])
    clock.tick()
    ing.ingest_docs([chat_doc("chat:slack:eng/3", 3, "Infra owns Ledger.")])
    rows = owns_rows(g)
    acts = Actions(g, clock)
    clock.tick()
    acts.confirm_fact(Actor("person:priya", client="test"), assertion_id=rows[I]["id"])
    clock.tick()
    assert (status_of(g, rows[I]["id"]), status_of(g, rows[P]["id"])) == ("current", "superseded")
    return ing, rows[P]["id"], rows[I]["id"], acts


def test_fx_r2_s6a_reexport_unchanged_row(g):
    clock = Clock(100)
    ing, Pid, Iid, acts = _s3_state(g, clock)
    before = (tuples(g), span_ts(g), evidence_edges(g, Pid), evidence_edges(g, Iid))
    n_src = len(sources(g))
    clock.tick()
    ing.ingest_docs([catalog_doc("catalog:backstage:services", 6, P, 2)])           # same row, updated_at t6
    assert len(sources(g)) == n_src + 1                                              # a new Source revision
    assert (tuples(g), span_ts(g), evidence_edges(g, Pid), evidence_edges(g, Iid)) == before
    assert len(evidence_edges(g, Pid)) == 1                                           # no new evidence edge (A56)
    assert acts._open_disputes(acts._assertion(Iid), clock()) == []


def test_fx_r2_s6b_reexport_changed_row_overrides_confirmation(g):
    clock = Clock(100)
    ing, Pid, Iid, acts = _s3_state(g, clock)
    clock.tick()
    ing.ingest_docs([catalog_doc("catalog:backstage:services", 6, P, 6)])           # row now says P from t6
    rows = g.ro("MATCH (a:Assertion {predicate:'OWNS', object_id:$l}) RETURN a.id AS id, a.subject_id AS s, "
                "a.valid_from AS vf, a.valid_to AS vt, a.status AS st, a.authority AS au ORDER BY vf", {"l": LEDGER})
    p6 = next(r for r in rows if r["s"] == P and r["vf"] == 6)
    assert (p6["st"], p6["au"], p6["vt"]) == ("current", 4, MAX)
    i = next(r for r in rows if r["id"] == Iid)
    assert (i["st"], i["vf"], i["vt"]) == ("superseded", 3, 6)
    found = acts.stale_detection(LEDGER)
    span6 = evidence_edges(g, p6["id"])[0]["span"]
    assert [(f["span"], f["why"]) for f in found if f["span"] == span6] == [(span6, "overrides a confirmation")]


# FX-R2-S9: route → confirm → undo route → undo confirm → re-confirm refused; ADR variant

def test_fx_r2_s9_withdraw_then_undo_confirmation(world):
    g, clock = world["g"], world["clock"]
    acts = Actions(g, clock)
    r = acts.route_to_owner(actor("person:eve"), ticket_id="ticket:rds-42")
    X = r["proposal"]
    clock.tick()
    c = acts.confirm_fact(actor("person:priya"), action_id=r["action_id"])
    N = c["produced"][0]
    now = clock.tick()
    h = history_facts(g, now, "ticket:rds-42", "ASSIGNED_TO")
    assert h[X]["status"] == "proposed" and status_of(g, N) == "current"
    assert h[X]["confirmed_by"] == {"assertion_id": N}                                       # confirmed, not pending
    acts.undo_action(actor("person:eve"), r["action_id"])                                      # undo R
    assert status_of(g, X) == "retracted" and status_of(g, N) == "current"
    assert g.ro("MATCH (ac:Action {id:$id}) RETURN ac.status AS s", {"id": r["action_id"]})[0]["s"] == "undone"
    clock.tick()
    acts.undo_action(actor("person:priya"), c["action_id"])                                    # undo the confirmation
    assert status_of(g, N) == "retracted" and status_of(g, X) == "retracted"
    clock.tick()
    with pytest.raises(Refused) as e:
        acts.confirm_fact(actor("person:priya"), action_id=r["action_id"])
    assert e.value.reason == f"withdrawn by the undo of Action {r['action_id']}"


def test_fx_r2_s9_adr_variant_draft_decision_hidden(world):
    g, clock, wp = world["g"], world["clock"], world["wp"]
    OLD, S = "decision:adr-001", LEDGER
    _fact(wp, "HAS_STATUS", OLD, "", 1, "sp7", value="accepted")
    _fact(wp, "AFFECTS", OLD, S, 1, "sp7")
    _fact(wp, "DECIDED_BY", OLD, "person:priya", 1, "sp7")
    acts = Actions(g, clock)
    clock.tick()
    d = acts.draft_adr_supersession(actor("person:eve"), OLD, "move to Aurora")
    NEW = d["decision"]
    clock.tick()
    c = acts.confirm_fact(actor("person:priya"), action_id=d["action_id"])
    clock.tick()
    acts.undo_action(actor("person:eve"), d["action_id"])
    assert g.ro("MATCH (d:Decision {id:$n}) RETURN d.status AS s", {"n": NEW})[0]["s"] == "accepted"   # still visible
    clock.tick()
    acts.undo_action(actor("person:priya"), c["action_id"])
    now = clock.tick()
    assert g.ro("MATCH (d:Decision {id:$n}) RETURN d.status AS s", {"n": NEW})[0]["s"] == ""
    assert g.ro("MATCH (d:Decision {id:$o}) RETURN d.status AS s", {"o": OLD})[0]["s"] == "accepted"
    pack = run_tool(Ctx(g, now=now), "trace_decision", {"entity_id": S})
    decided = {it["path"]["steps"][0]["node"]["id"] for it in pack["items"] if it.get("path")}
    assert OLD in decided and NEW not in decided                                                 # hidden
    assert g.ro("MATCH (d:Decision {id:$n}) RETURN count(d) AS n", {"n": NEW})[0]["n"] == 1      # kept for history
    with pytest.raises(Refused, match="withdrawn by the undo of Action"):
        acts.confirm_fact(actor("person:priya"), action_id=d["action_id"])
