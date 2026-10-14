"""Predicate registry: the single source of truth for Assertions, edges and tools (01 §4)."""
from __future__ import annotations

from dataclasses import dataclass

# Authority by statement form (01 §4.1, A21). There is no rank 3.
FORM_RANK = {"structured": 4, "confirmation": 4, "prose": 2, "chat": 1, "draft": 0}


@dataclass(frozen=True)
class Predicate:
    name: str
    subject_labels: tuple[str, ...]
    object_labels: tuple[str, ...]          # empty for literal predicates
    key_side: str                           # 'subject' | 'object' | 'none'
    confirmer: tuple[str, ...]              # rule names, OR-combined (01 §4.2)
    projection: str                         # edge type, or 'property:<name>'
    values: tuple[str, ...] = ()            # allowed literal values
    qualifier: str = ""
    statement: str = ""                     # template for the one-line statement

    @property
    def literal(self) -> bool:
        return bool(self.values)

    @property
    def functional(self) -> bool:
        return self.key_side in ("subject", "object")


P = Predicate
PREDICATES: dict[str, Predicate] = {}


def _add(p: Predicate) -> None:
    PREDICATES[key(p.name, p.qualifier)] = p


def key(name: str, qualifier: str = "") -> str:
    return f"{name}+{qualifier}" if qualifier else name


_add(P("OWNS", ("Team", "Person"), ("System", "Project"), "object", ("owner_lead:object",), "OWNS",
       statement="{s} owns {o}"))
_add(P("LEADS", ("Person",), ("Team", "Project"), "object", ("team_lead:object",), "LEADS",
       statement="{s} leads {o}"))
_add(P("MEMBER_OF", ("Person",), ("Team",), "subject", ("team_lead_primary:subject",), "MEMBER_OF",
       qualifier="primary", statement="{s} is a primary member of {o}"))
_add(P("MEMBER_OF", ("Person",), ("Team",), "none", ("team_lead:object",), "MEMBER_OF",
       statement="{s} is a member of {o}"))
_add(P("WORKS_ON", ("Person",), ("Project",), "none", ("owner_lead:object",), "WORKS_ON",
       statement="{s} works on {o}"))
_add(P("DEPENDS_ON", ("System",), ("System",), "none", ("owner_lead:subject",), "DEPENDS_ON",
       statement="{s} depends on {o}"))
_add(P("PART_OF", ("System",), ("Project",), "subject", ("owner_lead:subject",), "PART_OF",
       statement="{s} is part of {o}"))
_add(P("DECIDED_BY", ("Decision",), ("Person", "Team"), "none", ("deciders_replaced:subject",), "DECIDED_BY",
       statement="{s} was decided by {o}"))
_add(P("AFFECTS", ("Decision",), ("System", "Project"), "none", ("deciders_replaced:subject",), "AFFECTS",
       statement="{s} affects {o}"))
_add(P("REPLACES", ("Decision",), ("Decision",), "none", ("deciders:object",), "REPLACES",
       statement="{s} replaces {o}"))
_add(P("HAS_STATUS", ("Decision",), (), "subject", ("status_rule:subject",), "property:status",
       values=("proposed", "accepted", "superseded", "rejected"), statement="{s} is {v}"))
_add(P("ASSIGNED_TO", ("Ticket",), ("Person", "Team"), "subject", ("ticket_leads:subject",), "ASSIGNED_TO",
       statement="{s} is assigned to {o}"))
_add(P("HAS_STATE", ("Ticket",), (), "subject", ("ticket_leads:subject",), "property:state",
       values=("open", "in_progress", "done"), statement="{s} is {v}"))
_add(P("ABOUT", ("Ticket",), ("System", "Project"), "none", ("owner_lead:object",), "ABOUT",
       statement="{s} is about {o}"))

PROJECTION_TYPES = sorted({p.projection for p in PREDICATES.values() if not p.projection.startswith("property:")})


def get(name: str, qualifier: str = "") -> Predicate:
    return PREDICATES[key(name, qualifier)]


def chain_key(predicate: str, qualifier: str, subject_id: str, object_id: str) -> str:
    """02 §2 key encoding, used everywhere (A60)."""
    p = get(predicate, qualifier)
    pq = key(predicate, qualifier)
    if p.key_side == "object":
        return f"{pq}:{object_id}"
    if p.key_side == "subject":
        return f"{pq}:{subject_id}"
    return f"{pq}:{subject_id}>{object_id}"


def chain_id(predicate: str, qualifier: str, subject_id: str, object_id: str) -> str:
    return "ch_" + chain_key(predicate, qualifier, subject_id, object_id)


def key_id(predicate: str, qualifier: str, subject_id: str, object_id: str) -> str:
    p = get(predicate, qualifier)
    return object_id if p.key_side == "object" else subject_id if p.key_side == "subject" else ""


def render_statement(predicate: str, qualifier: str, s_name: str, o_name: str, value: str, negated: bool) -> str:
    p = get(predicate, qualifier)
    text = p.statement.format(s=s_name, o=o_name, v=value)
    return ("NOT: " + text) if negated else text


def label_of(entity_id: str) -> str:
    prefix = entity_id.split(":", 1)[0]
    return {"person": "Person", "team": "Team", "project": "Project", "system": "System",
            "decision": "Decision", "ticket": "Ticket"}[prefix]
