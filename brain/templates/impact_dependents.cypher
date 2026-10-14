// name: impact_dependents
// purpose: impact mode of find_paths (A73): systems with a DEPENDS_ON path into x valid at V, typed and bounded (R4, F6)
// params: x, V
// indexes: Entity.id, DEPENDS_ON.valid_to
// golden: tests/test_templates.py::test_goldens[impact_dependents]
MATCH p = (x:Entity {id:$x})<-[:DEPENDS_ON*1..3]-(s:Entity)
WHERE all(e IN relationships(p) WHERE e.valid_from <= $V AND e.valid_to > $V)
RETURN s.id AS id, s.name AS name, s.tier AS tier, length(p) AS hops,
       [n IN nodes(p) | n.id] AS node_ids, [e IN relationships(p) | e.aid] AS aids
ORDER BY hops ASC, tier ASC
LIMIT 20
