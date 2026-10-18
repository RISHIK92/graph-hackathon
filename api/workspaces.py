"""One FalkorDB graph per workspace (item 24 step 2): a small LRU registry of graph and agent, and the request's
current workspace in a context variable, set by the app's middleware from the session cookie.

A new workspace graph gets the full schema on first use (indexes, constraints, the guard sentinel and the
relationship-type registration of F23), so every query behaves on it as on the seeded graph.
"""
from __future__ import annotations

import re
import threading
from collections import OrderedDict
from contextvars import ContextVar
from dataclasses import dataclass

from brain import schema, snapshot
from brain.db import Graph

from .agent import Agent

MAX_OPEN = 32
_CP_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


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


def drop(name: str, port: int | None = None) -> None:
    """Delete a workspace's graph and its snapshot graphs; the next use starts it empty."""
    with _LOCK:
        _OPEN.pop(name, None)
    g = Graph(name=name) if port is None else Graph(name=name, port=port)
    snapshot.drop_all(g)
    g.delete()


def copy_into(src: Graph, name: str) -> None:
    """Replace a workspace's graph with a copy of src (GRAPH.COPY, on both 6.0.1 and 4.22.0: finding F29)."""
    drop(name)
    src.raw("GRAPH.COPY", src.name, name)


def _cp_graph_name(name: str, cp: str) -> str:
    if not _CP_NAME.match(cp):
        raise ValueError(f"invalid checkpoint name: {cp!r}")
    return f"{name}__cp_{cp}"


def _graph_list(g: Graph) -> set[str]:
    return {n.decode() if isinstance(n, bytes) else n for n in g.raw("GRAPH.LIST")}


def save_checkpoint(name: str, cp: str, port: int | None = None) -> str:
    """Snapshot a workspace graph to <name>__cp_<cp> via GRAPH.COPY."""
    target = _cp_graph_name(name, cp)
    src = Graph(name=name) if port is None else Graph(name=name, port=port)
    if name not in _graph_list(src):
        raise KeyError(f"workspace graph does not exist: {name}")
    dst = Graph(name=target) if port is None else Graph(name=target, port=port)
    dst.delete()
    src.raw("GRAPH.COPY", name, target)
    return target


def restore_checkpoint(name: str, cp: str, port: int | None = None) -> str:
    """Restore <name>__cp_<cp> into <name> via GRAPH.COPY, dropping snapshots and the workspace LRU entry."""
    src_name = _cp_graph_name(name, cp)
    src = Graph(name=src_name) if port is None else Graph(name=src_name, port=port)
    if src_name not in _graph_list(src):
        raise KeyError(f"unknown checkpoint: {cp}")
    drop(name, port=port)
    src.raw("GRAPH.COPY", src_name, name)
    cur = _CURRENT.get()
    if cur and cur.g.name == name:
        cur.agent._index = None
        cur.agent.turn_log.clear()
    return src_name


def drop_checkpoints(name: str, port: int | None = None) -> None:
    """Delete all <name>__cp_* checkpoint graphs for a workspace."""
    g = Graph(name=name) if port is None else Graph(name=name, port=port)
    prefix = f"{name}__cp_"
    for k in sorted(_graph_list(g)):
        if k.startswith(prefix):
            (Graph(name=k) if port is None else Graph(name=k, port=port)).delete()


def current() -> Workspace | None:
    return _CURRENT.get()


def enter(w: Workspace):
    return _CURRENT.set(w)


def leave(token) -> None:
    _CURRENT.reset(token)
