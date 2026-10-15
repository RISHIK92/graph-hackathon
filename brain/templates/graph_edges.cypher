// name: graph_edges
// purpose: every projection edge between entities valid at V (GET /graph)
// params: V
// indexes: none (the whole-graph view; bounded by the world size)
// golden: tests/test_templates.py::test_goldens[graph_edges]
MATCH (a:Entity)-[e]->(b:Entity)
WHERE e.aid IS NOT NULL AND e.valid_from <= $V AND e.valid_to > $V
RETURN a.id AS source, b.id AS target, type(e) AS type, e.aid AS aid, e.valid_from AS vf,
       e.valid_to AS vt, e.authority AS authority
