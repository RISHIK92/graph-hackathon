// name: any_person
// purpose: the first Person by id, the fallback demo identity
// params: none
// indexes: none (LIMIT 1 over the Person label)
// golden: tests/test_templates.py::test_goldens[any_person]
MATCH (p:Person)
RETURN p.id AS id ORDER BY p.id LIMIT 1
