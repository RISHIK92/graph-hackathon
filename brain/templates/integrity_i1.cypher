// name: integrity_i1
// purpose: open runs per chain among current assertions (I1: at most one)
// params: none
// indexes: none (an integrity sweep over every current assertion)
// golden: tests/test_templates.py::test_goldens[integrity_i1]
MATCH (a:Assertion)
WHERE a.status = 'current'
RETURN a.chain_id AS c, collect(DISTINCT a.run_id) AS runs
