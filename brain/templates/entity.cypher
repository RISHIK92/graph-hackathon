// name: entity
// purpose: one entity's name, description and labels (entity panel)
// params: id
// indexes: Entity.id
// golden: tests/test_templates.py::test_goldens[entity]
MATCH (e:Entity {id:$id})
RETURN e.name AS name, e.description AS d, labels(e) AS labels
