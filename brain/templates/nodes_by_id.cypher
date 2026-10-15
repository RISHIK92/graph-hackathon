// name: nodes_by_id
// purpose: entity nodes by id (GET /graph/neighbourhood)
// params: ids
// indexes: Entity.id
// golden: tests/test_templates.py::test_goldens[nodes_by_id]
UNWIND $ids AS i
MATCH (n:Entity {id:i})
RETURN n.id AS id, n.name AS name, labels(n) AS labels
