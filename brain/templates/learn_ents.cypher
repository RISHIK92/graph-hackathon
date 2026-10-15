// name: learn_ents
// purpose: names and aliases of the entities a learned fact names
// params: ids
// indexes: Entity.id
// golden: tests/test_templates.py::test_goldens[learn_ents]
MATCH (e:Entity)
WHERE e.id IN $ids
RETURN e.id AS id, e.name AS n, e.aliases AS a
