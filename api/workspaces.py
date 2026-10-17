"""One FalkorDB graph per workspace (item 24 step 2): a small LRU registry of graph and agent, and the request's
current workspace in a context variable, set by the app's middleware from the session cookie.

A new workspace graph gets the full schema on first use (indexes, constraints, the guard sentinel and the
relationship-type registration of F23), so every query behaves on it as on the seeded graph.
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from contextvars import ContextVar
from dataclasses import dataclass

from brain import schema, snapshot
from brain.db import Graph

from .agent import Agent

MAX_OPEN = 32


@dataclass
class Workspace:
    g: Graph
    agent: Agent


_OPEN: OrderedDict[str, Workspace] = OrderedDict()
_LOCK = threading.Lock()
_CURRENT: ContextVar[Workspace | None] = ContextVar("workspace", default=None)


def get(name: str) -> Workspace:
    with _LOCK:
        w = _OPEN.get(name)
        if w:
            _OPEN.move_to_end(name)
            return w
    g = Graph(name=name)
    try:
        ready = g.ro("CALL db.constraints() YIELD label RETURN count(label) AS n", template="schema")[0]["n"] > 0
    except Exception:  # noqa: BLE001 - a graph that doesn't exist yet: "empty key"
        ready = False
    if not ready:
        schema.create(g)
    w = Workspace(g, Agent(g))
    with _LOCK:
        _OPEN[name] = w
        while len(_OPEN) > MAX_OPEN:
            _OPEN.popitem(last=False)
    return w


def drop(name: str) -> None:
    """Delete a workspace's graph and its snapshot graphs; the next use starts it empty."""
    with _LOCK:
        _OPEN.pop(name, None)
    g = Graph(name=name)
    snapshot.drop_all(g)
    g.delete()


def copy_into(src: Graph, name: str) -> None:
    """Replace a workspace's graph with a copy of src (GRAPH.COPY, on both 6.0.1 and 4.22.0: finding F29)."""
    drop(name)
    src.raw("GRAPH.COPY", src.name, name)


def current() -> Workspace | None:
    return _CURRENT.get()


def enter(w: Workspace):
    return _CURRENT.set(w)


def leave(token) -> None:
    _CURRENT.reset(token)
