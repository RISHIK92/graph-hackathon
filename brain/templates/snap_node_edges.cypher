// name: snap_node_edges
// purpose: an entity's own live edges in a snapshot graph, either direction, to cite a knowledge gap that is an absence (item 20)
// params: id
// indexes: N.id
// golden: tests/test_templates.py::test_goldens[snap_node_edges]
MATCH (n:N {id:$id})
WITH n
MATCH (n)-[e:OWNS|LEADS|MEMBER_OF|DEPENDS_ON|WORKS_ON|PART_OF]-(x:N)
RETURN type(e) AS type, x.id AS id, e.aid AS aid
ORDER BY aid
