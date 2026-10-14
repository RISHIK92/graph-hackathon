"""FalkorDB access. Reads go through RO_QUERY with an explicit timeout (R9); writes report counters (F18)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from falkordb import FalkorDB

from .config import settings


def cypher_value(v: Any) -> str:
    """Parameter literal for the `CYPHER k=v` header (R10). The client's own serialiser writes
    Python booleans as `True`/`False`, which the header parser does not read as booleans."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(cypher_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ",".join(f"`{k}`:{cypher_value(x)}" for k, x in v.items()) + "}"
    raise TypeError(f"unsupported parameter type {type(v)}")


def with_params(cypher: str, params: dict | None) -> str:
    if not params:
        return cypher
    return "CYPHER " + " ".join(f"{k}={cypher_value(v)}" for k, v in params.items()) + " " + cypher


class GuardFailed(Exception):
    """The unique-constraint sentinel fired (README F17, A51): the whole query rolled back."""


class WriteMismatch(Exception):
    """Zero guard rows, or write counters that differ from the plan (README F18, I12)."""


@dataclass
class QueryLog:
    template: str
    cypher: str
    params: dict
    rows: int
    ms: float


@dataclass
class WriteResult:
    rows: list[list[Any]]
    header: list[str]
    counters: dict[str, int]


@dataclass
class Graph:
    name: str = settings.graph
    host: str = settings.falkor_host
    port: int = settings.falkor_port
    log: list[QueryLog] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.db = FalkorDB(host=self.host, port=self.port)
        self.g = self.db.select_graph(self.name)

    # reads
    def ro(self, cypher: str, params: dict | None = None, timeout: int | None = None,
           template: str = "adhoc") -> list[dict]:
        t0 = time.perf_counter()
        res = self.g.ro_query(with_params(cypher, params), timeout=timeout or settings.timeout_default)
        rows = _rows(res)
        self.log.append(QueryLog(template, cypher, params or {}, len(rows),
                                 (time.perf_counter() - t0) * 1000))
        return rows

    # writes
    def write(self, cypher: str, params: dict | None = None, template: str = "adhoc",
              timeout: int | None = None) -> WriteResult:
        t0 = time.perf_counter()
        try:
            res = self.g.query(with_params(cypher, params), timeout=timeout or settings.timeout_max)
        except Exception as e:  # noqa: BLE001 - redis ResponseError
            if "unique constraint" in str(e).lower():
                raise GuardFailed(str(e)) from e
            raise
        counters = {k: int(getattr(res, k) or 0) for k in (
            "nodes_created", "nodes_deleted", "relationships_created",
            "relationships_deleted", "properties_set")}
        self.log.append(QueryLog(template, cypher, params or {}, len(res.result_set or []),
                                 (time.perf_counter() - t0) * 1000))
        return WriteResult(res.result_set or [], [h[1] for h in (res.header or [])], counters)

    def raw(self, *args: Any) -> Any:
        return self.db.connection.execute_command(*args)

    def explain(self, cypher: str, params: dict | None = None) -> str:
        """GRAPH.EXPLAIN text (an EXPLAIN prefix is rejected on 6.0.1, F15)."""
        return str(self.g.explain(with_params(cypher, params)))

    def delete(self) -> None:
        try:
            self.g.delete()
        except Exception:  # noqa: BLE001 - graph may not exist
            pass

    def module_version(self) -> int:
        for mod in self.raw("MODULE", "LIST"):
            d = _pairs(mod)
            if d.get("name") in ("graph", b"graph"):
                return int(d["ver"])
        return 0


def _pairs(mod: Any) -> dict:
    if isinstance(mod, dict):
        return {(k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
                for k, v in mod.items()}
    it = list(mod)
    out = {}
    for i in range(0, len(it) - 1, 2):
        k = it[i].decode() if isinstance(it[i], bytes) else it[i]
        v = it[i + 1].decode() if isinstance(it[i + 1], bytes) else it[i + 1]
        out[k] = v
    return out


def _rows(res: Any) -> list[dict]:
    header = [h[1] if isinstance(h, (list, tuple)) else h for h in (res.header or [])]
    return [dict(zip(header, [_plain(v) for v in row])) for row in (res.result_set or [])]


def _plain(v: Any) -> Any:
    if hasattr(v, "properties") and hasattr(v, "labels"):
        d = dict(v.properties)
        d["_labels"] = list(v.labels)
        return d
    if hasattr(v, "properties") and hasattr(v, "relation"):
        d = dict(v.properties)
        d["_type"] = v.relation
        return d
    if isinstance(v, list):
        return [_plain(x) for x in v]
    return v
