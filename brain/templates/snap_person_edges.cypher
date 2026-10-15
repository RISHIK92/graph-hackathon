// name: snap_person_edges
// purpose: a person's lead, membership and work edges in a snapshot graph, to cite a ranking (key_people, item 17)
// params: id
// indexes: N.id
// golden: tests/test_templates.py::test_goldens[snap_person_edges]
MATCH (p:N {id:$id})
WITH p
MATCH (p)-[e:LEADS|MEMBER_OF|WORKS_ON]->(x:N)
RETURN type(e) AS type, x.id AS id, x.name AS name, e.aid AS aid
