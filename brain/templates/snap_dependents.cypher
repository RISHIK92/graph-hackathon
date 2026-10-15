// name: snap_dependents
// purpose: the direct DEPENDS_ON edges into a system in a snapshot graph, to cite a ranking (critical_systems, item 17)
// params: id
// indexes: N.id
// golden: tests/test_templates.py::test_goldens[snap_dependents]
MATCH (s:N {id:$id})
WITH s
MATCH (d:N)-[e:DEPENDS_ON]->(s)
RETURN d.id AS id, d.name AS name, e.aid AS aid
