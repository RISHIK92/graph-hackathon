// name: snap_owns
// purpose: every current OWNS edge in a snapshot graph, to cite a gap (knowledge_gaps, item 17)
// params: none
// indexes: none (every OWNS edge; one per owned thing)
// golden: tests/test_templates.py::test_goldens[snap_owns]
MATCH (o:N)-[e:OWNS]->(x:N)
RETURN o.id AS owner, x.id AS id, e.aid AS aid
