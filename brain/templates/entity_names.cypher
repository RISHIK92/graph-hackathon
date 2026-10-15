// name: entity_names
// purpose: every entity id and name, for statements and write-path names
// params: none
// indexes: none (the whole entity list; bounded by the world size)
// golden: tests/test_templates.py::test_goldens[entity_names]
MATCH (e:Entity)
RETURN e.id AS id, e.name AS n
