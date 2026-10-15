// name: dispute_edge
// purpose: the endpoints and statement of a disputing assertion (GET /graph side list)
// params: id
// indexes: Assertion.id
// golden: tests/test_templates.py::test_goldens[dispute_edge]
MATCH (a:Assertion {id:$id})
RETURN a.subject_id AS s, a.object_id AS o, a.statement AS st
