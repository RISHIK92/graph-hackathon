// name: statement
// purpose: one assertion's statement
// params: id
// indexes: Assertion.id
// golden: tests/test_templates.py::test_goldens[statement]
MATCH (a:Assertion {id:$id})
RETURN a.statement AS s
