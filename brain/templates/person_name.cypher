// name: person_name
// purpose: one person's name (action summaries)
// params: id
// indexes: Person.id
// golden: tests/test_templates.py::test_goldens[person_name]
MATCH (p:Person {id:$id})
RETURN p.name AS n
