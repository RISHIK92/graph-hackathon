// name: run_members
// purpose: every assertion in a run (evidence for a projection edge is the union over its run, 02 §3)
// params: run
// indexes: Assertion.run_id
// golden: tests/test_templates.py::test_goldens[run_members]
MATCH (a:Assertion {run_id:$run})
RETURN a.id AS id
