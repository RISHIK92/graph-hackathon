"""Template rule R2 (README §3) and the 06 §1 rows "Template goldens" and "Index use".

Every `.cypher` template in brain/templates runs on a small hand-built fixture graph, on both FalkorDB
versions (conftest `g`), and is checked four ways in one test per template:

1. golden rows: hand-written expected values for the key fields (ids, names, aids), not a recording;
2. an EXPLAIN snapshot under tests/snapshots/<version>/<template>.txt, written on first run and
   compared afterwards (`SNAPSHOT_UPDATE=1` rewrites; a diff fails with a unified diff);
3. index use: the plan contains an index scan for the anchor named first in the header's `indexes:`;
4. label leak (F4): no Traverse/Expand/Scan operator gives a template variable a label the template
   did not give it (6.0.1 attached a comprehension's `:Assertion` to an outer variable, README F4).

Known per-version failures are listed in KNOWN_FAILURES with the reason; a listed check that passes
fails the test so the list can't go stale.
"""
from __future__ import annotations

import difflib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from brain import providers, snapshot, store, templates
from brain.actions import Actions, Actor
from brain.config import MAX
from brain.db import Graph, with_params
from brain.registry import PROJECTION_TYPES
from brain.write_path import Candidate, WritePath

from .conftest import PORTS, Clock, make_span, seed_basic

SNAP_DIR = Path(__file__).parent / "snapshots"
ENTITY_LABELS = {"Entity", "Person", "Team", "Project", "System", "Decision", "Ticket"}
INDEX_OPS = ("Node By Index Scan", "Edge By Index Scan", "Node By Fulltext Index Scan",
             "Node By Vector Index Scan", "ProcedureCall")   # ProcedureCall: 4.22.0's fulltext/vector entry

# (template, version, check) -> reason. Observed Oct 2026 on the fixture below; see the module docstring.
KNOWN_FAILURES: dict[tuple[str, str, str], str] = {
}


# fixture graph

TEXTS = {
    "sp_lead": "Priya leads Payments", "sp_own_old": "Platform owns Ledger", "sp_own": "Payments owns Ledger",
    "sp_chat": "Infra owns Ledger", "sp_dep1": "Checkout depends on Ledger",
    "sp_dep2": "Storefront depends on Checkout", "sp_part": "Ledger is part of Commerce",
    "sp_own_proj": "Platform owns Commerce", "sp_adr": "ADR-002 replaces ADR-001 and affects Ledger",
    "sp_about": "RDS-42 is about Ledger",
}


@dataclass
class Fixture:
    g: Graph
    version: str
    ids: dict[str, str]
    now: int
    memo: dict = field(default_factory=dict)

    def vec(self, text: str) -> list[float]:
        return providers.embed([text])[0]


@pytest.fixture
def fx(g, clock) -> Fixture:
    """Payments owns Ledger (from t=5, after Platform t=1..5) with Priya leading Payments; Infra's chat
    claim is a disputed challenger; Storefront -> Checkout -> Ledger DEPENDS_ON; Ledger PART_OF Commerce
    which Platform owns; ADR-002 REPLACES ADR-001, AFFECTS Ledger, DECIDED_BY Priya, MOTIVATED_BY sp_adr,
    accepted; RDS-42 ABOUT Ledger; one route_to_owner proposal (RDS-42 -> Priya, draft source)."""
    version = next(v for v, p in PORTS.items() if p == g.port)
    seed_basic(g)
    store.upsert_entities(g, [
        {"id": "system:checkout", "name": "Checkout", "aliases": [], "tier": 1},
        {"id": "system:storefront", "name": "Storefront", "aliases": [], "tier": 2},
        {"id": "project:commerce", "name": "Commerce", "aliases": []},
        {"id": "decision:adr-002", "name": "ADR-002", "aliases": [], "title": "Move Ledger to Postgres",
         "decided_at": 3},
    ])
    g.write("UNWIND $rows AS x MATCH (n:Entity {id:x.id}) SET n.embedding = vecf32(x.e)",
            {"rows": [{"id": i, "e": providers.embed([n])[0]} for i, n in
                      [("system:ledger", "Ledger"), ("team:payments", "Payments"), ("person:priya", "Priya Raman")]]})
    for sid, text in TEXTS.items():
        make_span(g, sid, text, 1)
    g.write("UNWIND $rows AS x MATCH (s:Span {id:x.id}) SET s.embedding = vecf32(x.e)",
            {"rows": [{"id": sid, "e": providers.embed([t])[0]} for sid, t in TEXTS.items()]})
    store.create_source(g, {"id": "sess1", "doc_key": "chat_session:brain:sess1", "kind": "chat_session",
                            "status": "active", "is_latest": True, "ingested_at": 1, "user_id": "u1"})
    make_span(g, "turn1", "who owns ledger?", 7, src="sess1", kind="chat_session", role="user")
    make_span(g, "turn2", "Payments owns Ledger.", 8, src="sess1", kind="chat_session", role="agent")
    store.add_mentions(g, [{"span_id": "sp_own", "entity_id": "system:ledger", "start": 0, "end": 6,
                            "method": "exact", "hedged": False}])
    store.add_authored_by(g, [{"span_id": "sp_own", "person_id": "person:bob"}])

    wp = WritePath(g, clock)
    ids: dict[str, str] = {}

    def fact(pred, s, o, vf, span, form="structured", value=""):
        plan = wp.new_plan()
        out = wp.add_candidate(plan, Candidate(pred, s, o, object_value=value, valid_from=vf, span_id=span,
                                               quote_end=len(TEXTS[span]), form=form, source_id="src:test"))
        wp.execute(plan)
        clock.tick()
        return out["assertion_id"]

    ids["lead"] = fact("LEADS", "person:priya", "team:payments", 1, "sp_lead")
    ids["own_old"] = fact("OWNS", "team:platform", "system:ledger", 1, "sp_own_old")
    ids["own"] = fact("OWNS", "team:payments", "system:ledger", 5, "sp_own")
    ids["chat"] = fact("OWNS", "team:infra", "system:ledger", 6, "sp_chat", form="chat")
    ids["dep1"] = fact("DEPENDS_ON", "system:checkout", "system:ledger", 1, "sp_dep1")
    ids["dep2"] = fact("DEPENDS_ON", "system:storefront", "system:checkout", 1, "sp_dep2")
    ids["part"] = fact("PART_OF", "system:ledger", "project:commerce", 1, "sp_part")
    ids["own_proj"] = fact("OWNS", "team:platform", "project:commerce", 1, "sp_own_proj")
    ids["replaces"] = fact("REPLACES", "decision:adr-002", "decision:adr-001", 3, "sp_adr")
    ids["affects"] = fact("AFFECTS", "decision:adr-002", "system:ledger", 3, "sp_adr")
    ids["decided"] = fact("DECIDED_BY", "decision:adr-002", "person:priya", 3, "sp_adr")
    ids["status"] = fact("HAS_STATUS", "decision:adr-002", "", 3, "sp_adr", value="accepted")
    ids["about"] = fact("ABOUT", "ticket:rds-42", "system:ledger", 1, "sp_about")
    store.add_motivated_by(g, "decision:adr-002", "sp_adr", "context", clock())
    r = Actions(g, clock).route_to_owner(Actor("person:eve", client="test"), ticket_id="ticket:rds-42")
    ids["proposal"], ids["action"] = r["proposal"], r["action_id"]
    clock.tick(10)
    return Fixture(g, version, ids, clock())


# Some templates read state the base fixture lacks; their params build it first (per test, so other
# goldens are unaffected). Writes land after f.now, so reads that need them use the returned time.

def _confirm_routing(f) -> dict:
    """Priya confirms Eve's routing proposal (RDS-42 -> Priya)."""
    if "routing" in f.memo:
        return f.memo["routing"]
    clock = Clock(f.now + 1)
    r = Actions(f.g, clock).confirm_fact(Actor("person:priya", client="test"), action_id=f.ids["action"])
    f.ids["confirm"], f.ids["confirmed"] = r["action_id"], r["produced"][0]
    f.memo["routing"] = {"action_id": r["action_id"], "produced": r["produced"][0], "t": clock.tick()}
    return f.memo["routing"]


def _override(f) -> int:
    """Priya confirms Payments' ownership, then a later structured span says Platform owns Ledger again."""
    clock = Clock(f.now + 1)
    f.ids["own_confirm"] = Actions(f.g, clock).confirm_fact(Actor("person:priya", client="test"),
                                                            assertion_id=f.ids["own"])["action_id"]
    make_span(f.g, "sp_over", "Platform owns Ledger", clock.tick())
    wp = WritePath(f.g, clock)
    plan = wp.new_plan(clock.tick())
    f.ids["over"] = wp.add_candidate(plan, Candidate("OWNS", "team:platform", "system:ledger", valid_from=8,
                                                     span_id="sp_over", quote_end=20, form="structured",
                                                     source_id="src:test"))["assertion_id"]
    wp.execute(plan)
    return clock()


def _membership(f) -> int:
    """Priya's primary MEMBER_OF Payments (the base fixture has no membership)."""
    clock = Clock(f.now + 1)
    make_span(f.g, "sp_mem", "Priya is in Payments", clock())
    wp = WritePath(f.g, clock)
    plan = wp.new_plan(clock.tick())
    f.ids["member"] = wp.add_candidate(plan, Candidate("MEMBER_OF", "person:priya", "team:payments", qualifier="primary",
                                                       valid_from=1, span_id="sp_mem", quote_end=20,
                                                       form="structured", source_id="src:test"))["assertion_id"]
    wp.execute(plan)
    return clock.tick()


def _draft_adr(f) -> str:
    """Priya drafts a supersession of ADR-002."""
    r = Actions(f.g, Clock(f.now + 1)).draft_adr_supersession(Actor("person:priya", client="test"),
                                                             "decision:adr-002", "Move to Aurora")
    f.ids["draft_decision"] = r["decision"]
    return r["action_id"]


# parameters and golden rows per template

PARAMS = {
    "action": lambda f: {"id": f.ids["action"]},
    "action_draft": lambda f: {"id": f.ids["action"]},
    "action_evidence": lambda f: {"ac": _confirm_routing(f)["action_id"], "max": MAX},
    "action_log": lambda f: {"p": "person:eve"},
    "action_read": lambda f: {"id": f.ids["action"]},
    "action_targets": lambda f: {"id": f.ids["action"]},
    "all_entities": lambda f: {},
    "already_confirmed": lambda f: {"id": f.ids["proposal"], "now": _confirm_routing(f)["t"]},
    "any_confirmed": lambda f: {"id": f.ids["action"], "now": _confirm_routing(f)["t"]},
    "any_person": lambda f: {},
    "assertion": lambda f: {"id": f.ids["own"]},
    "assertions_by_id": lambda f: {"ids": [f.ids["own"], f.ids["chat"]]},
    "based_on_spans": lambda f: {"runs": [f.ids["affects"], f.ids["status"]], "max": MAX},
    "belief_all_leads": lambda f: {"now": f.now},
    "belief_lead_of": lambda f: {"t": "team:payments", "now": f.now},
    "belief_out_edges": lambda f: {"x": "decision:adr-002", "rel": "AFFECTS", "now": f.now},
    "belief_owners_of": lambda f: {"x": "system:ledger", "now": f.now},
    "belief_parent_of": lambda f: {"x": "system:ledger", "now": f.now},
    "belief_primary_team": lambda f: {"p": "person:priya", "now": _membership(f)},
    "chain_meta": lambda f: {"c": "ch_OWNS:system:ledger"},
    "chains_for_entity": lambda f: {"e": "system:ledger", "p": "OWNS"},
    "confirmed_proposals": lambda f: {"ac": _confirm_routing(f)["action_id"]},
    "confirmed_targets": lambda f: {"ac": _confirm_routing(f)["action_id"]},
    "confirms_of": lambda f: (_confirm_routing(f), {"ids": [f.ids["proposal"], f.ids["own"]]})[1],
    "current_in_chain": lambda f: {"c": "ch_OWNS:system:ledger"},
    "decision_status": lambda f: {"d": "decision:adr-002"},
    "decision_trace": lambda f: {"d": "decision:adr-002", "V": f.now, "T": f.now},
    "decisions_affecting": lambda f: {"x": "system:ledger", "V": f.now},
    "demo_identity": lambda f: {},
    "depends_on": lambda f: {"id": "system:checkout", "V": f.now},
    "directory_decisions": lambda f: {"V": f.now},
    "directory_people": lambda f: {"V": f.now},
    "directory_projects": lambda f: {"V": f.now},
    "directory_systems": lambda f: {"V": f.now},
    "directory_tickets": lambda f: {"V": f.now},
    "dispute_chains": lambda f: {"max": MAX},
    "dispute_edge": lambda f: {"id": f.ids["chat"]},
    "disputed_run": lambda f: {"id": f.ids["chat"], "max": MAX},
    "doc_evidence": lambda f: {"k": "src:test"},
    "draft_decision": lambda f: {"id": _draft_adr(f)},
    "draft_status": lambda f: {"id": f.g.q("action_draft", {"id": f.ids["action"]})[0]["id"]},
    "entity": lambda f: {"id": "system:ledger"},
    "entity_name": lambda f: {"id": "system:ledger"},
    "entity_names": lambda f: {},
    "entity_sources": lambda f: {"id": "system:ledger"},
    "evidence_fragment": lambda f: {"aids": [f.ids["own"], f.ids["proposal"]], "T": f.now},
    "existing_spans": lambda f: {"ids": ["sp_own", "sp_nope"]},
    "experts_signals": lambda f: {"x": "system:ledger", "V": f.now},
    "graph_edge_kinds": lambda f: {"aids": [f.ids["own"], f.ids["dep1"]], "max": MAX},
    "graph_edges": lambda f: {"V": f.now},
    "graph_mentioned": lambda f: {"k": ["wiki"]},
    "graph_nodes": lambda f: {},
    "graph_ticks": lambda f: {},
    "group_counts": lambda f: {"label": "Team", "p": "LEADS", "dir": "in", "member_label": "Person", "primary": False,
                               "V": f.now},
    "impact_dependents": lambda f: {"x": "system:ledger", "V": f.now},
    "integrity_chains": lambda f: {},
    "integrity_i1": lambda f: {},
    "integrity_i11": lambda f: (f.g.write("UNWIND range(1, 51) AS i CREATE (:Assertion {id:'as_cap' + toString(i), "
                                          "chain_id:'ch_cap'})"), {})[1],
    "integrity_i5": lambda f: (f.g.write("CREATE (:Assertion {id:'as_bare', chain_id:'ch_bare'})"), {})[1],
    "integrity_sentinel": lambda f: {},
    "latest_spans": lambda f: {"l": "src:test"},
    "lead_at": lambda f: {"t": "team:payments", "V": f.now},
    "learn_ents": lambda f: {"ids": ["team:payments", "system:ledger"]},
    "link_exact": lambda f: {"q": "ledger-service"},
    "link_fulltext": lambda f: {"q": "ledger"},
    "link_vector": lambda f: {"k": 3, "vec": f.vec("Ledger")},
    "live_confirmations": lambda f: {"run": _confirm_routing(f)["produced"], "now": f.now + 5},
    "names": lambda f: {"ids": ["ledger", "person:priya", "nope"]},
    "neighbourhood": lambda f: {"ids": ["system:checkout"], "V": f.now, "h": 1},
    "nodes_by_id": lambda f: {"ids": ["system:ledger", "team:payments"]},
    "overview_decisions": lambda f: {"V": f.now},
    "overview_pending": lambda f: {},
    "overview_teams": lambda f: {"V": f.now},
    "owner_at": lambda f: {"x": "system:ledger", "V": f.now},
    "owner_inherited": lambda f: {"x": "system:ledger", "V": f.now},
    "owner_previous": lambda f: {"x": "system:ledger", "V": f.now},
    "past_belief_members": lambda f: {"members": [f.ids["own"]], "T": f.now},
    "past_belief_run": lambda f: {"chain": "ch_OWNS:system:ledger", "T": f.now, "V": f.now},
    "paths_between": lambda f: {"a": "system:ledger", "b": "person:priya", "V": f.now, "h": 2, "types": ["OWNS", "LEADS"]},
    "pending_proposals": lambda f: {},
    "people": lambda f: {"V": f.now},
    "person_name": lambda f: {"id": "person:priya"},
    "produced_assertions": lambda f: {"id": f.ids["action"]},
    "produced_sources": lambda f: {"id": f.ids["action"]},
    "proposal_ends": lambda f: {"p": f.ids["proposal"]},
    "proposal_links": lambda f: {"ids": [f.ids["proposal"]], "now": f.now},
    "proposals_about": lambda f: {"e": "ticket:rds-42"},
    "rationale_spans": lambda f: {"d": "decision:adr-002", "max": MAX},
    "recent_actions": lambda f: {"u": "person:eve"},
    "related_at": lambda f: {"a": "system:ledger", "p": "DEPENDS_ON", "dir": "in", "label": "System", "primary": False,
                             "V": f.now},
    "replaced_by": lambda f: {"d": "decision:adr-001", "V": f.now},
    "replaces_out": lambda f: {"d": "decision:adr-002", "V": f.now},
    "revisions": lambda f: {"k": "src:test"},
    "run_members": lambda f: {"run": f.ids["own"]},
    "search_fulltext": lambda f: {"q": "ledger"},
    "search_vector": lambda f: {"k": 4, "vec": f.vec("Payments owns Ledger")},
    "session": lambda f: {"id": "sess1"},
    "session_spans": lambda f: {"user": "u1"},
    "source_exists": lambda f: {"id": "src:test"},
    "source_view": lambda f: {"id": "src:test"},
    "snap_betweenness": lambda f: {"_graph": _snap(f), "n": 100, "seed": 7},
    "snap_dependents": lambda f: {"_graph": _snap(f), "id": "system:ledger"},
    "snap_leaders": lambda f: {"_graph": _snap(f)},
    "snap_meta": lambda f: {"_graph": _snap(f)},
    "snap_node_count": lambda f: {"_graph": _snap(f)},
    "snap_owns": lambda f: {"_graph": _snap(f)},
    "snap_pagerank": lambda f: {"_graph": _snap(f)},
    "snap_paths": lambda f: {"_graph": _snap(f), "a": "person:priya", "b": "system:ledger", "types": list(snapshot.EDGE_TYPES)},
    "snap_person_edges": lambda f: {"_graph": _snap(f), "id": "person:priya"},
    "snap_wcc": lambda f: {"_graph": _snap(f)},
    "snapshot_touches": lambda f: {"V": f.now},
    "snapshot_version": lambda f: {},
    "span_details": lambda f: {"sids": ["sp_own", "turn1"], "T": f.now},
    "span_facts": lambda f: {"sids": ["sp_own_old", "sp_own"], "max": MAX},
    "span_view": lambda f: {"id": "sp_own", "max": MAX},
    "stale_detection": lambda f: {"max": MAX, "e": "team:platform"},
    "stale_override": lambda f: (_override(f), {"max": MAX})[1],
    "stated_by_latest": lambda f: {"s": "src:test"},
    "statement": lambda f: {"id": f.ids["own"]},
    "strongest_member": lambda f: {"r": f.ids["own"]},
    "ticket_about": lambda f: {"t": "ticket:rds-42", "m": MAX},
    "turn_count": lambda f: {"s": "sess1"},
    "turn_span": lambda f: {"id": "turn1", "src": "sess1"},
    "unsupported": lambda f: (f.g.write("MATCH (a:Assertion {id:$id})-[e:EVIDENCED_BY]->() SET e.removed_at = 1",
                                        {"id": f.ids["dep2"]}), {"max": MAX})[1],
    "withdrawn_by": lambda f: {"id": f.ids["proposal"]},
}


def _by(rows, key):
    return {r[key]: r for r in rows}


def g_action_read(f, rows):
    assert len(rows) == 1
    r = rows[0]
    assert r["action"]["id"] == f.ids["action"] and r["action"]["kind"] == "route_to_owner"
    assert r["action"]["actor"] == "person:eve" and r["action"]["status"] == "done"
    assert set(r["based_on"]) == {f.ids["about"], f.ids["own"], f.ids["lead"]}
    assert r["produced"] == [f.ids["proposal"]]
    assert len(r["sources"]) == 1 and r["sources"][0].startswith("src_draft_")
    assert r["targets"] == ["ticket:rds-42"]


def g_assertions_by_id(f, rows):
    r = _by(rows, "assertion_id")
    assert set(r) == {f.ids["own"], f.ids["chat"]}
    own, chat = r[f.ids["own"]], r[f.ids["chat"]]
    assert (own["predicate"], own["subject_id"], own["object_id"]) == ("OWNS", "team:payments", "system:ledger")
    assert (own["status"], own["authority"], own["valid_from"], own["valid_to"]) == ("current", 4, 5, MAX)
    assert own["run_id"] == f.ids["own"] and own["chain_id"] == "ch_OWNS:system:ledger"
    assert own["statement"] == "Payments owns Ledger" and own["retracted_at"] == MAX and own["negated"] is False
    assert (chat["subject_id"], chat["status"], chat["authority"], chat["run_id"]) == ("team:infra", "disputed", 1, "")


def g_chains_for_entity(f, rows):
    assert rows == [{"chain": "ch_OWNS:system:ledger", "q": ""}]


def g_decision_trace(f, rows):
    assert len(rows) == 1
    r = rows[0]
    assert (r["id"], r["name"], r["title"], r["decided_at"]) == ("decision:adr-002", "ADR-002", "Move Ledger to Postgres", 3)
    assert (r["status"], r["status_aid"]) == ("accepted", f.ids["status"])
    assert set(r["replaced"]) == {"decision:adr-002", "decision:adr-001"}      # *0.. includes d itself
    assert r["affects"] == [{"id": "system:ledger", "name": "Ledger", "aid": f.ids["affects"]}]
    assert r["motivated"] == [{"span": "sp_adr", "section": "context", "action_id": ""}]
    assert r["deciders"] == [{"id": "person:priya", "name": "Priya Raman", "aid": f.ids["decided"]}]


def g_decisions_affecting(f, rows):
    assert rows == [{"id": "decision:adr-002", "name": "ADR-002", "title": "Move Ledger to Postgres",
                     "status": "accepted", "aid": f.ids["affects"]}]


def g_evidence_fragment(f, rows):
    r = _by(rows, "aid")
    assert set(r) == {f.ids["own"], f.ids["proposal"]}
    assert r[f.ids["own"]]["evs"] == [{"span": "sp_own", "form": "structured", "authority": 4, "qs": 0,
                                       "qe": len(TEXTS["sp_own"]), "src": "src:test"}]
    assert r[f.ids["proposal"]]["evs"] == []     # rank-0 draft evidence is dropped (A59)


def g_experts_signals(f, rows):
    assert len(rows) == 1
    r = rows[0]
    assert r["authored"] == [{"person": "person:bob", "kind": "authored", "ref": "sp_own", "ts": 1}]
    assert r["leads"] == [{"person": "person:priya", "kind": "LEADS", "ref": f.ids["lead"], "ts": 1}]
    assert [x for x in r["direct"] if x["person"]] == []           # no Person owns Ledger directly
    assert [x for x in r["tickets"] if x["person"]] == []          # the routing is only proposed
    assert [x for x in r["decided"] if x["person"]] == [
        {"person": "person:priya", "kind": "DECIDED_BY", "ref": f.ids["decided"], "ts": 3}]


def g_impact_dependents(f, rows):
    assert [(r["id"], r["name"], r["tier"], r["hops"]) for r in rows] == [
        ("system:checkout", "Checkout", 1, 1), ("system:storefront", "Storefront", 2, 2)]
    assert rows[0]["node_ids"] == ["system:ledger", "system:checkout"] and rows[0]["aids"] == [f.ids["dep1"]]
    assert rows[1]["node_ids"] == ["system:ledger", "system:checkout", "system:storefront"]
    assert rows[1]["aids"] == [f.ids["dep1"], f.ids["dep2"]]


def g_lead_at(f, rows):
    assert rows == [{"lead": "person:priya", "name": "Priya Raman", "aid": f.ids["lead"], "vf": 1, "vt": MAX,
                     "authority": 4}]


def g_link_exact(f, rows):
    assert [(r["id"], r["name"]) for r in rows] == [("system:ledger", "Ledger")]
    assert set(rows[0]["labels"]) == {"Entity", "System"}


def g_link_fulltext(f, rows):
    assert [(r["id"], r["name"]) for r in rows] == [("system:ledger", "Ledger")]
    assert rows[0]["score"] > 0


def g_link_vector(f, rows):
    assert rows[0]["id"] == "system:ledger" and abs(rows[0]["score"]) < 1e-5     # distance 0 to itself
    assert {r["id"] for r in rows} == {"system:ledger", "team:payments", "person:priya"}
    assert [r["score"] for r in rows] == sorted(r["score"] for r in rows)        # ascending (R6)


def g_owner_at(f, rows):
    assert rows == [{"owner": "team:payments", "name": "Payments", "aid": f.ids["own"], "vf": 5, "vt": MAX,
                     "authority": 4}]


def g_owner_inherited(f, rows):
    assert rows == [{"owner": "team:platform", "name": "Platform", "aid": f.ids["own_proj"], "vf": 1, "vt": MAX,
                     "authority": 4, "via": "project:commerce", "via_name": "Commerce", "via_aid": f.ids["part"]}]


def g_owner_previous(f, rows):
    assert rows == [{"owner": "team:platform", "name": "Platform", "aid": f.ids["own_old"], "vf": 1, "vt": 5,
                     "authority": 4}]


def g_past_belief_members(f, rows):
    assert len(rows) == 1
    r = rows[0]
    assert r["id"] == f.ids["own"] and r["valid_from"] == 5
    assert len(r["evs"]) == 1
    assert dict(r["evs"][0]) == {"span": "sp_own", "form": "structured", "authority": 4, "ts": 1}
    assert r["sup_vfs"] == []
    assert len(r["challengers"]) == 1
    assert dict(r["challengers"][0]) == {"id": f.ids["chat"], "last_ts": 1}


def g_past_belief_run(f, rows):
    assert len(rows) == 1
    r = rows[0]
    assert r["id"] == f.ids["own"]
    assert (r["subject_id"], r["object_id"], r["object_value"]) == ("team:payments", "system:ledger", "")
    assert r["negated"] is False and r["valid_from"] == 5
    assert r["others"] == []


def g_proposal_links(f, rows):
    assert rows == [{"id": f.ids["proposal"], "producers": [f.ids["action"]], "confirmed_by": []}]


def g_proposals_about(f, rows):
    assert rows == [{"id": f.ids["proposal"]}]


def g_replaced_by(f, rows):
    assert rows == [{"id": "decision:adr-002", "aid": f.ids["replaces"]}]


def g_run_members(f, rows):
    assert rows == [{"id": f.ids["own"]}]


def g_search_fulltext(f, rows):
    assert {r["id"] for r in rows} == {"sp_own_old", "sp_own", "sp_chat", "sp_dep1", "sp_part", "sp_adr",
                                       "sp_about", "turn1"}            # turn2 is an agent span (excluded)
    assert _by(rows, "id")["turn1"] == {"id": "turn1", "ts": 7, "kind": "chat_session", "score": rows[0]["score"]}


def g_search_vector(f, rows):
    assert rows[0]["id"] == "sp_own" and abs(rows[0]["score"]) < 1e-5
    assert "turn2" not in {r["id"] for r in rows}                               # agent span filtered after YIELD
    assert [r["score"] for r in rows] == sorted(r["score"] for r in rows)
    assert all(r["kind"] == "wiki" for r in rows)


def g_session_spans(f, rows):
    assert rows == [{"id": "turn1", "text": "who owns ledger?", "ts": 7}]


def _snap(f) -> Graph:
    if "snap" not in f.memo:
        f.memo["snap"] = snapshot.snapshot(f.g, None, f.now)
    return f.memo["snap"]


def g_snapshot_touches(f, rows):
    assert rows == [{"person": "person:bob", "target": "system:ledger", "w": 1}]


def g_snapshot_version(f, rows):
    assert len(rows) == 1 and rows[0]["n"] > 0 and rows[0]["actions"] >= 1 and rows[0]["last"] > 0


def g_snap_meta(f, rows):
    assert len(rows) == 1 and rows[0]["V"] == f.now and rows[0]["version"].count(":") == 3


def g_snap_pagerank(f, rows):
    order = [r["id"] for r in sorted(rows, key=lambda r: (-r["score"], r["name"]))]
    assert order == ["system:ledger", "system:checkout", "system:storefront"]   # ranks, never scores (F25)


def g_snap_dependents(f, rows):
    assert rows == [{"id": "system:checkout", "name": "Checkout", "aid": f.ids["dep1"]}]


def g_snap_betweenness(f, rows):
    assert {r["id"] for r in rows} == {"person:priya", "person:bob", "person:eve"}
    assert all(r["score"] >= 0 for r in rows)


def g_snap_person_edges(f, rows):
    assert rows == [{"type": "LEADS", "id": "team:payments", "name": "Payments", "aid": f.ids["lead"]}]


def g_snap_wcc(f, rows):
    comp = {r["id"]: r["c"] for r in rows}
    ledger = {i for i, c in comp.items() if c == comp["system:ledger"]}
    assert ledger == {"system:ledger", "team:payments", "person:priya", "project:commerce", "team:platform"}
    assert comp["system:checkout"] != comp["system:ledger"]
    assert ("Team" in next(r["labels"] for r in rows if r["id"] == "team:payments"))


def g_snap_node_count(f, rows):
    assert rows == [{"n": 13}]


def g_snap_leaders(f, rows):
    assert rows == [{"person": "person:priya", "team": "team:payments", "aid": f.ids["lead"]}]


def g_snap_owns(f, rows):
    assert sorted((r["owner"], r["id"], r["aid"]) for r in rows) == sorted([
        ("team:payments", "system:ledger", f.ids["own"]), ("team:platform", "project:commerce", f.ids["own_proj"])])


def g_snap_paths(f, rows):
    paths = {tuple(r["ids"]) for r in rows}   # 4.22.0 may repeat a path per parallel edge; callers de-duplicate
    assert paths == {("person:priya", "team:payments", "system:ledger"), ("person:priya", "decision:adr-002", "system:ledger")}
    rels = next(r["rels"] for r in rows if r["ids"][1] == "team:payments")
    assert [(x["type"], x["from"]) for x in rels] == [("LEADS", "person:priya"), ("OWNS", "team:payments")]


def g_span_facts(f, rows):
    assert sorted((r["span"], r["statement"], r["status"]) for r in rows) == [
        ("sp_own", "Payments owns Ledger", "current"), ("sp_own_old", "Platform owns Ledger", "superseded")]
    assert next(r["valid_to"] for r in rows if r["span"] == "sp_own_old") == 5


def g_span_details(f, rows):
    r = _by(rows, "id")
    assert set(r) == {"sp_own", "turn1"}
    assert (r["sp_own"]["text"], r["sp_own"]["ts"], r["sp_own"]["kind"], r["sp_own"]["role"]) == (
        TEXTS["sp_own"], 1, "wiki", "human")
    assert r["sp_own"]["revs"] == [{"src": "src:test", "title": "src:test", "uri": "", "kind": "wiki",
                                    "doc_key": "src:test", "cs": 0, "ce": len(TEXTS["sp_own"]), "live": True}]
    assert r["turn1"]["role"] == "user"
    assert [(x["src"], x["kind"], x["live"]) for x in r["turn1"]["revs"]] == [("sess1", "chat_session", True)]


NULL_REF = {"id": None, "name": None}


def g_action_draft(f, rows):
    assert len(rows) == 1 and rows[0]["id"].startswith("src_draft_")


def g_action_log(f, rows):
    assert [(r["id"], r["kind"], r["status"]) for r in rows] == [(f.ids["action"], "route_to_owner", "done")]


def g_any_person(f, rows):
    assert rows == [{"id": "person:bob"}]


def g_demo_identity(f, rows):
    assert rows == []                                   # the fixture has no world_meta Source


def g_depends_on(f, rows):
    assert rows == [{"id": "system:ledger", "name": "Ledger", "aid": f.ids["dep1"]}]


def g_directory_decisions(f, rows):
    r = _by(rows, "id")
    assert list(r) == ["decision:adr-001", "decision:adr-002"]
    new = r["decision:adr-002"]
    assert (new["title"], new["status"]) == ("Move Ledger to Postgres", "accepted")
    assert new["affects"] == [{"id": "system:ledger", "name": "Ledger", "aid": f.ids["affects"]}]
    assert new["deciders"] == [{"id": "person:priya", "name": "Priya Raman"}]
    assert new["replaces"] == [{"id": "decision:adr-001", "name": "ADR-001"}]
    assert r["decision:adr-001"]["replaced_by"] == [{"id": "decision:adr-002", "name": "ADR-002"}]


def g_directory_people(f, rows):
    r = _by(rows, "id")
    assert list(r) == ["person:bob", "person:eve", "person:priya"]
    assert r["person:priya"]["leads"] == [{"id": "team:payments", "name": "Payments"}]
    assert r["person:priya"]["decides"] == [{"id": "decision:adr-002", "name": "ADR-002"}]
    assert r["person:priya"]["team"] == NULL_REF and r["person:priya"]["tickets"] == 0   # routing only proposed


def g_directory_projects(f, rows):
    assert len(rows) == 1
    r = rows[0]
    assert r["id"] == "project:commerce"
    assert r["owner"] == {"id": "team:platform", "name": "Platform", "aid": f.ids["own_proj"]}
    assert r["systems"] == [{"id": "system:ledger", "name": "Ledger"}] and r["people"] == 0


def g_directory_systems(f, rows):
    r = _by(rows, "id")
    assert list(r) == ["system:checkout", "system:ledger", "system:storefront"]
    led = r["system:ledger"]
    assert led["owner"] == {"id": "team:payments", "name": "Payments", "aid": f.ids["own"]}
    assert led["project"] == {"id": "project:commerce", "name": "Commerce"}
    assert (led["depends_on"], led["depended_on_by"], led["decisions"]) == (0, 1, 1)
    assert (r["system:checkout"]["depends_on"], r["system:checkout"]["depended_on_by"]) == (1, 1)


def g_directory_tickets(f, rows):
    assert len(rows) == 1
    r = rows[0]
    assert r["id"] == "ticket:rds-42" and r["about"] == {"id": "system:ledger", "name": "Ledger"}
    assert r["assignee"]["id"] is None and r["state"] is None      # the routing is only proposed


def g_dispute_chains(f, rows):
    assert rows == [{"chain": "ch_OWNS:system:ledger"}]


def g_dispute_edge(f, rows):
    assert rows == [{"s": "team:infra", "o": "system:ledger", "st": "Infra owns Ledger"}]


def g_draft_status(f, rows):
    assert rows == [{"s": "done"}]


def g_entity(f, rows):
    assert rows == [{"name": "Ledger", "d": "", "labels": ["Entity", "System"]}]


def g_entity_sources(f, rows):
    assert rows == [{"kind": "wiki", "sources": [{"id": "src:test", "title": "src:test", "author": None, "at": None}]}]


def g_graph_edge_kinds(f, rows):
    assert _by(rows, "aid") == {f.ids["own"]: {"aid": f.ids["own"], "kinds": ["wiki"]},
                                f.ids["dep1"]: {"aid": f.ids["dep1"], "kinds": ["wiki"]}}


def g_graph_edges(f, rows):
    got = {(r["source"], r["type"], r["target"]): r for r in rows}
    assert set(got) == {
        ("team:payments", "OWNS", "system:ledger"), ("team:platform", "OWNS", "project:commerce"),
        ("system:ledger", "PART_OF", "project:commerce"), ("person:priya", "LEADS", "team:payments"),
        ("ticket:rds-42", "ABOUT", "system:ledger"), ("system:checkout", "DEPENDS_ON", "system:ledger"),
        ("system:storefront", "DEPENDS_ON", "system:checkout"), ("decision:adr-002", "AFFECTS", "system:ledger"),
        ("decision:adr-002", "DECIDED_BY", "person:priya"), ("decision:adr-002", "REPLACES", "decision:adr-001")}
    own = got[("team:payments", "OWNS", "system:ledger")]   # not Platform's ended claim nor Infra's disputed one
    assert (own["aid"], own["vf"], own["vt"], own["authority"]) == (f.ids["own"], 5, MAX, 4)


def g_graph_mentioned(f, rows):
    assert rows == [{"id": "system:ledger"}]


def g_graph_nodes(f, rows):
    r = _by(rows, "id")
    assert len(r) == 13 and r["system:ledger"] == {"id": "system:ledger", "name": "Ledger", "labels": ["Entity", "System"],
                                                   "decided_at": None}
    assert r["decision:adr-002"]["decided_at"] == 3


def g_graph_ticks(f, rows):
    assert [r["t"] for r in rows] == [1, 3, 5] and all(r["n"] >= 1 for r in rows)
    assert next(r["n"] for r in rows if r["t"] == 3) == 3   # ADR-002 REPLACES, AFFECTS, DECIDED_BY edges


def g_names(f, rows):
    assert sorted(rows, key=lambda r: r["id"]) == [
        {"id": "person:priya", "name": "Priya Raman", "labels": ["Entity", "Person"]},
        {"id": "system:ledger", "name": "Ledger", "labels": ["Entity", "System"]}]   # "ledger" by bare id


def g_neighbourhood(f, rows):
    assert sorted((r["source"], r["type"], r["target"], r["aid"]) for r in rows) == [
        ("system:checkout", "DEPENDS_ON", "system:ledger", f.ids["dep1"]),
        ("system:storefront", "DEPENDS_ON", "system:checkout", f.ids["dep2"])]       # h=1: no Ledger edges


def g_nodes_by_id(f, rows):
    assert [r["id"] for r in rows] == ["system:ledger", "team:payments"]


def g_overview_decisions(f, rows):
    assert rows == [{"id": "decision:adr-002", "name": "ADR-002", "title": "Move Ledger to Postgres",
                     "aid": f.ids["status"], "affects": [{"id": "system:ledger", "name": "Ledger", "aid": f.ids["affects"]}]}]


def g_overview_pending(f, rows):
    assert [(r["action_id"], r["kind"]) for r in rows] == [(f.ids["action"], "route_to_owner")]


def g_overview_teams(f, rows):
    r = _by(rows, "id")
    assert list(r) == ["team:infra", "team:payments", "team:platform"]
    assert r["team:payments"]["leads"] == [{"id": "person:priya", "name": "Priya Raman", "aid": f.ids["lead"]}]
    assert r["team:payments"]["owns"] == [{"id": "system:ledger", "name": "Ledger", "aid": f.ids["own"]}]
    assert r["team:platform"]["owns"] == [{"id": "project:commerce", "name": "Commerce", "aid": f.ids["own_proj"]}]
    assert [x for x in r["team:infra"]["owns"] if x["id"]] == []       # Infra's chat claim is disputed


def g_pending_proposals(f, rows):
    assert [(r["action_id"], r["actor"]) for r in rows] == [(f.ids["action"], "person:eve")]


def g_people(f, rows):
    r = _by(rows, "id")
    assert list(r) == ["person:bob", "person:eve", "person:priya"]
    assert (r["person:priya"]["leads"], r["person:priya"]["decides"]) == (["Payments"], ["ADR-002"])


def g_source_view(f, rows):
    assert len(rows) == 1 and rows[0]["source"]["id"] == "src:test"
    assert {s["span"] for s in rows[0]["spans"]} == set(TEXTS)


def g_span_view(f, rows):
    assert rows == [{"text": "Payments owns Ledger", "kind": "wiki", "ts": 1, "author": "", "role": "human", "revisions": [
        {"source": "src:test", "title": "src:test", "uri": "", "cs": 0, "ce": 20, "latest": True, "live": True}]}]


def g_statement(f, rows):
    assert rows == [{"s": "Payments owns Ledger"}]


def g_action(f, rows):
    assert len(rows) == 1
    ac = rows[0]["ac"]
    assert (ac["id"], ac["kind"], ac["actor"], ac["status"]) == (f.ids["action"], "route_to_owner", "person:eve", "done")


def g_action_evidence(f, rows):
    assert [r["aid"] for r in rows] == [f.ids["confirmed"]] and rows[0]["sid"].startswith("sp_")


def g_action_targets(f, rows):
    assert rows == [{"id": "ticket:rds-42"}]


def g_already_confirmed(f, rows):
    assert rows == [{"c": f.ids["confirmed"], "ac": f.ids["confirm"]}]


def g_any_confirmed(f, rows):
    assert rows == [{"c": f.ids["confirmed"]}]


def g_assertion(f, rows):
    assert len(rows) == 1
    r = rows[0]
    assert (r["id"], r["predicate"], r["subject_id"], r["object_id"]) == (f.ids["own"], "OWNS", "team:payments", "system:ledger")
    assert (r["status"], r["run_id"], r["chain_id"], r["valid_from"], r["retracted_at"]) == (
        "current", f.ids["own"], "ch_OWNS:system:ledger", 5, MAX)


def g_based_on_spans(f, rows):
    assert rows == [{"id": "sp_adr"}]


def g_belief_all_leads(f, rows):
    assert rows == [{"person": "person:priya", "name": "Priya Raman", "team": "team:payments", "aid": f.ids["lead"]}]


def g_belief_lead_of(f, rows):
    assert rows == [{"person": "person:priya", "name": "Priya Raman", "aid": f.ids["lead"]}]


def g_belief_out_edges(f, rows):
    assert rows == [{"id": "system:ledger", "name": "Ledger", "aid": f.ids["affects"]}]


def g_belief_owners_of(f, rows):
    assert rows == [{"owner": "team:payments", "name": "Payments", "aid": f.ids["own"]}]   # not Infra's rank-1 chat


def g_belief_parent_of(f, rows):
    assert rows == [{"parent": "project:commerce", "aid": f.ids["part"]}]


def g_belief_primary_team(f, rows):
    assert rows == [{"team": "team:payments", "aid": f.ids["member"]}]


def g_confirmed_proposals(f, rows):
    assert rows == [{"id": f.ids["proposal"]}]


def g_confirmed_targets(f, rows):
    assert rows == [{"id": f.ids["confirmed"]}]


def g_current_in_chain(f, rows):
    assert rows == [{"id": f.ids["own"], "st": "Payments owns Ledger"}]


def g_decision_status(f, rows):
    assert rows == [{"s": "accepted", "aid": f.ids["status"], "n": "ADR-002"}]


def g_disputed_run(f, rows):
    assert rows == [{"run": f.ids["own"]}]


def g_draft_decision(f, rows):
    assert rows == [{"d": f.ids["draft_decision"]}]


def g_entity_name(f, rows):
    assert rows == [{"n": "Ledger"}]


def g_entity_names(f, rows):
    r = {x["id"]: x["n"] for x in rows}
    assert len(r) == 13 and r["person:priya"] == "Priya Raman"


def g_learn_ents(f, rows):
    assert sorted(rows, key=lambda r: r["id"]) == [
        {"id": "system:ledger", "n": "Ledger", "a": ["ledger", "ledger-service"]},
        {"id": "team:payments", "n": "Payments", "a": ["payments"]}]


def g_live_confirmations(f, rows):
    assert [(r["member"], r["action_id"]) for r in rows] == [(f.ids["confirmed"], f.ids["confirm"])]


def g_produced_assertions(f, rows):
    assert rows == [{"id": f.ids["proposal"]}]


def g_produced_sources(f, rows):
    assert len(rows) == 1 and rows[0]["id"].startswith("src_draft_")


def g_rationale_spans(f, rows):
    assert rows == [{"id": "sp_adr"}]


def g_stale_detection(f, rows):
    assert [(r["span"], r["aid"], r["why"], r["valid_to"]) for r in rows] == [("sp_own_old", f.ids["own_old"], "stale", 5)]


def g_stale_override(f, rows):
    assert [(r["span"], r["aid"], r["why"]) for r in rows] == [("sp_over", f.ids["over"], "overrides a confirmation")]


def g_strongest_member(f, rows):
    assert rows == [{"id": f.ids["own"], "au": 4}]


def g_turn_span(f, rows):
    assert rows == [{"text": "who owns ledger?", "role": "user", "ts": 7}]


def g_withdrawn_by(f, rows):
    assert rows == [{"ac": f.ids["action"], "s": "done"}]


FIXTURE_CHAINS = {"own": "ch_OWNS:system:ledger", "lead": "ch_LEADS:team:payments", "part": "ch_PART_OF:system:ledger",
                  "own_proj": "ch_OWNS:project:commerce", "status": "ch_HAS_STATUS:decision:adr-002"}


def g_all_entities(f, rows):
    r = _by(rows, "id")
    assert len(r) == 13 and r["system:ledger"]["aliases"] == ["ledger", "ledger-service"]


def g_chain_meta(f, rows):
    assert rows == [{"p": "OWNS", "q": "", "k": "system:ledger"}]


def g_doc_evidence(f, rows):
    got = {(r["span"], r["aid"]) for r in rows}
    assert {(sid, f.ids[k]) for sid, k in [("sp_own", "own"), ("sp_chat", "chat"), ("sp_adr", "affects")]} <= got
    assert len(got) == 13 and all(r["rm"] == MAX and r["rb"] == "" for r in rows)
    assert f.ids["proposal"] not in {r["aid"] for r in rows}         # draft evidence carries an action_id


def g_existing_spans(f, rows):
    assert rows == [{"id": "sp_own", "ts": 1}]


def g_integrity_chains(f, rows):
    r = _by(rows, "id")
    assert len(r) == 12 and r["ch_OWNS:system:ledger"] == {"id": "ch_OWNS:system:ledger", "p": "OWNS", "q": "",
                                                           "k": "system:ledger"}


def g_integrity_i1(f, rows):
    r = {x["c"]: x["runs"] for x in rows}
    assert all(len(v) == 1 for v in r.values())
    assert r["ch_OWNS:system:ledger"] == [f.ids["own"]]       # Platform's is superseded, Infra's disputed


def g_integrity_i11(f, rows):
    assert rows == [{"c": "ch_cap", "n": 51}]


def g_integrity_i5(f, rows):
    assert rows == [{"id": "as_bare"}]


def g_integrity_sentinel(f, rows):
    assert rows == [{"n": 1}]


def g_latest_spans(f, rows):
    assert {r["id"] for r in rows} == set(TEXTS)


def g_revisions(f, rows):
    assert rows == [{"id": "src:test", "updated_at": 1, "is_latest": True, "ingested_at": 1, "status": "active"}]


def g_source_exists(f, rows):
    assert rows == [{"ingested_at": 1, "is_latest": True}]


def g_stated_by_latest(f, rows):
    got = {(r["chain"], r["aid"]) for r in rows}
    assert {(c, f.ids[k]) for k, c in FIXTURE_CHAINS.items()} <= got and len(got) == 13


def g_unsupported(f, rows):
    assert rows == [{"aid": f.ids["dep2"]}]


def g_confirms_of(f, rows):
    assert rows == [{"proposal": f.ids["proposal"], "confirmed": f.ids["confirmed"], "status": "current",
                     "action": f.ids["confirm"]}]                  # own is not a proposal: no row


def g_paths_between(f, rows):
    assert [[n["id"] for n in r["ns"]] for r in rows] == [["system:ledger", "team:payments", "person:priya"]]
    assert [(e["type"], e["aid"], e["from"]) for e in rows[0]["es"]] == [
        ("OWNS", f.ids["own"], "team:payments"), ("LEADS", f.ids["lead"], "person:priya")]


def g_person_name(f, rows):
    assert rows == [{"n": "Priya Raman"}]


def g_proposal_ends(f, rows):
    assert rows == [{"s": "ticket:rds-42", "o": "person:priya"}]


def g_recent_actions(f, rows):
    assert rows == [{"id": f.ids["action"]}]


def g_replaces_out(f, rows):
    assert rows == [{"o": "decision:adr-001", "name": "ADR-001", "title": None, "aid": f.ids["replaces"]}]


def g_session(f, rows):
    assert rows == [{"u": "u1", "a": None}]


def g_ticket_about(f, rows):
    assert rows == [{"x": "system:ledger"}]


def g_turn_count(f, rows):
    assert rows == [{"n": 2}]


def g_group_counts(f, rows):
    assert [(r["id"], r["n"]) for r in rows] == [("team:payments", 1), ("team:infra", 0), ("team:platform", 0)]
    assert rows[0]["ms"] == [{"id": "person:priya", "name": "Priya Raman", "aid": f.ids["lead"]}]


def g_related_at(f, rows):
    assert rows == [{"id": "system:checkout", "name": "Checkout", "aid": f.ids["dep1"]}]   # not Storefront (2 hops)


GOLDENS = {k[2:]: v for k, v in globals().items() if k.startswith("g_") and callable(v)}


# plan helpers

def explain_lines(g: Graph, cypher: str, params: dict) -> list[str]:
    """Raw GRAPH.EXPLAIN, normalised. The client's ExecutionPlan string is lossy (it cuts `OWNS|LEADS`
    at the bar and drops operators), so the raw reply is used."""
    out = g.raw("GRAPH.EXPLAIN", g.name, with_params(cypher, params))
    lines = [x.decode() if isinstance(x, bytes) else str(x) for x in out]

    def sort_types(m: re.Match) -> str:   # 6.0.1/4.22 prints a multi-type edge's types in varying order
        types = [t.lstrip(":") for t in m.group(2).split("|")]
        return "[" + m.group(1) + ":" + "|".join(sorted(types)) + m.group(3)

    return [re.sub(r"\[(\w*):([\w:|]+\|[\w:|]+)([\]*])", sort_types, re.sub(r"[_@]anon_(\d+)", r"anon_\1", ln.rstrip()))
            for ln in lines]


def check_snapshot(version: str, name: str, plan: list[str]) -> None:
    path = SNAP_DIR / version / f"{name}.txt"
    text = "\n".join(plan) + "\n"
    if os.environ.get("SNAPSHOT_UPDATE") == "1" or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return
    old = path.read_text()
    if old != text:
        diff = "\n".join(difflib.unified_diff(old.splitlines(), text.splitlines(), "stored", "current", lineterm=""))
        raise AssertionError(f"EXPLAIN plan for {name} on {version} differs from {path.relative_to(SNAP_DIR.parent)} "
                             f"(a plan change is a review item, R2; SNAPSHOT_UPDATE=1 rewrites):\n{diff}")


def check_index(name: str, plan: list[str]) -> None:
    indexes = templates.header(name)["indexes"]
    if indexes.startswith("none"):     # an intentional scan must say why
        assert re.fullmatch(r"none \(.+\)", indexes), f"{name}: `indexes: none` needs a reason in parentheses"
        return
    anchor = indexes.split(",")[0].strip()
    text = "\n".join(plan)
    if anchor.startswith("full-text"):
        ok = "Fulltext Index Scan" in text or "ProcedureCall" in text
    elif anchor.startswith("vector"):
        ok = "Vector Index Scan" in text or "ProcedureCall" in text
    else:
        label = anchor.split(".")[0]
        labels = ENTITY_LABELS if label == "Entity" else {label}
        ok = any(re.search(rf"Node By Index Scan \| \(\w+:{lab}\)", text) for lab in labels)
    assert ok, f"{name}: no index scan for anchor {anchor!r} in plan:\n{text}"


def template_labels(name: str) -> dict[str, set[str]]:
    """Variable -> labels the template body itself gives it (empty set: declared without a label)."""
    body = templates.body(name)
    out: dict[str, set[str]] = {}
    for var, label in re.findall(r"\((\w+)(?::(\w+))?\s*[{)]", body):
        out.setdefault(var, set())
        if label:
            out[var].add(label)
    return out


def check_label_leak(name: str, plan: list[str]) -> None:
    allowed = template_labels(name)
    leaks = []
    for ln in plan:
        if not any(op in ln for op in ("Traverse", "Expand", "Scan")):
            continue
        for var, label in re.findall(r"\((\w+):(\w+)[^)]*\)", ln):
            if var in allowed and label not in allowed[var]:
                leaks.append(f"{var} gained :{label} (template gives it {sorted(allowed[var]) or 'no label'}) in: {ln.strip()}")
    assert not leaks, f"{name}: label leak (README F4, R2):\n" + "\n".join(leaks)


def _run_checks(fx: Fixture, name: str, checks: list[tuple[str, callable]]) -> None:
    unexpected, expected = [], []
    for check, fn in checks:
        key = (name, fx.version, check)
        try:
            fn()
        except AssertionError as e:
            if key in KNOWN_FAILURES:
                expected.append(f"{check}: {KNOWN_FAILURES[key]}")
            else:
                unexpected.append(f"[{check}] {e}")
        else:
            if key in KNOWN_FAILURES:
                unexpected.append(f"[{check}] passes on {fx.version}; remove it from KNOWN_FAILURES")
    if unexpected:
        pytest.fail("\n".join(unexpected))
    if expected:
        pytest.xfail("\n".join(expected))


# tests

@pytest.mark.parametrize("name", templates.all_names())
def test_goldens(fx: Fixture, name: str):
    params = dict(PARAMS[name](fx))
    g = params.pop("_graph", fx.g)   # snapshot-graph templates (item 17) run on the snapshot their params build
    rows = g.ro(templates.body(name), params, template=name)
    plan = explain_lines(g, templates.body(name), params)
    _run_checks(fx, name, [
        ("golden", lambda: GOLDENS[name](fx, rows)),
        ("snapshot", lambda: check_snapshot(fx.version, name, plan)),
        ("index", lambda: check_index(name, plan)),
        ("label_leak", lambda: check_label_leak(name, plan)),
    ])


def test_every_template_has_params_and_golden():
    assert set(PARAMS) == set(templates.all_names()) == set(GOLDENS)


@pytest.mark.parametrize("name", templates.all_names())
def test_header(name: str):
    """`// golden:` names a test in this file and `// params:` covers every `$param` in the body."""
    h = templates.header(name)
    m = re.fullmatch(r"tests/test_templates\.py::(\w+)\[(\w+)\]", h["golden"])
    assert m, f"{name}: golden header {h['golden']!r} is not tests/test_templates.py::<test>[<template>]"
    assert m.group(1) in globals() and callable(globals()[m.group(1)]), f"{name}: no test {m.group(1)}"
    assert m.group(2) == name
    declared = {p.strip().split(" ")[0] for p in h["params"].split(",")}
    used = set(re.findall(r"\$(\w+)", templates.body(name)))
    assert used <= declared, f"{name}: body uses {sorted(used - declared)} not listed in `// params:`"
    for k in h["indexes"], h["purpose"], h["name"]:
        assert k
    assert h["name"] == name


@pytest.mark.parametrize("name", ["neighbourhood", "paths_between"])
def test_path_template_types_match_registry(name: str):
    """These templates hard-code the projection types (a type list can't be a parameter)."""
    m = re.search(r"\[:([A-Z_|]+)\*1\.\.\d\]", templates.body(name))
    assert m and m.group(1).split("|") == PROJECTION_TYPES


def test_readme_cypher_section_matches_templates():
    """The README lists the shipped Cypher (07 §3); `python -m brain.readme` regenerates it."""
    from brain import readme
    text = (Path(__file__).parent.parent / "README.md").read_text()
    block = text[text.index(readme.START) + len(readme.START):text.index(readme.END)]
    assert block.strip() == readme.section().strip(), "README Cypher section is stale: run `python -m brain.readme`"
