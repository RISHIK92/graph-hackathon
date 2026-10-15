// name: integrity_i5
// purpose: up to 20 assertions without any evidence edge (I5)
// params: none
// indexes: none (an integrity sweep over every assertion)
// golden: tests/test_templates.py::test_goldens[integrity_i5]
MATCH (a:Assertion)
WHERE NOT (a)-[:EVIDENCED_BY]->()
RETURN a.id AS id LIMIT 20
