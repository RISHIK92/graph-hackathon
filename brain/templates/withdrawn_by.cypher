// name: withdrawn_by
// purpose: the action that produced an assertion, with its status (withdrawn-by-undo refusals)
// params: id
// indexes: Assertion.id
// golden: tests/test_templates.py::test_goldens[withdrawn_by]
MATCH (ac:Action)-[:PRODUCED]->(p:Assertion {id:$id})
RETURN ac.id AS ac, ac.status AS s
