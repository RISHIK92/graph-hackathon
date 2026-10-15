// name: all_entities
// purpose: every entity with name and aliases, for the ingestion alias index
// params: none
// indexes: none (the whole entity list; bounded by the world size)
// golden: tests/test_templates.py::test_goldens[all_entities]
MATCH (e:Entity)
RETURN e.id AS id, e.name AS name, e.aliases AS aliases
