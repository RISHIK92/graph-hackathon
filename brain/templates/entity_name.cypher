// name: entity_name
// purpose: one entity's name
// params: id
// indexes: Entity.id
// golden: tests/test_templates.py::test_goldens[entity_name]
MATCH (e:Entity {id:$id})
RETURN e.name AS n
