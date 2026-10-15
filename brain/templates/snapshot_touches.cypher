// name: snapshot_touches
// purpose: how many spans each person authored that mention each entity, up to V; the snapshot graph's derived TOUCHES {w} edges (item 17)
// params: V
// indexes: none (scans authored spans; bounded by the world size)
// golden: tests/test_templates.py::test_goldens[snapshot_touches]
MATCH (p:Person)<-[:AUTHORED_BY]-(s:Span)-[:MENTIONS]->(x:Entity)
WHERE s.ts <= $V AND p.id <> x.id
RETURN p.id AS person, x.id AS target, count(DISTINCT s) AS w
