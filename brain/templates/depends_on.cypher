// name: depends_on
// purpose: what an entity depends on at V (entity panel)
// params: id, V
// indexes: Entity.id
// golden: tests/test_templates.py::test_goldens[depends_on]
MATCH (x:Entity {id:$id})-[d:DEPENDS_ON]->(y)
WHERE d.valid_from <= $V AND d.valid_to > $V
RETURN y.id AS id, y.name AS name, d.aid AS aid
