// name: names
// purpose: id or bare id (without the label prefix) to name and labels, for chips (GET /names)
// params: ids
// indexes: none (the bare-id suffix match can't use the id index)
// golden: tests/test_templates.py::test_goldens[names]
MATCH (e:Entity) WHERE e.id IN $ids OR any(i IN $ids WHERE e.id ENDS WITH (':' + i))
RETURN e.id AS id, e.name AS name, labels(e) AS labels
