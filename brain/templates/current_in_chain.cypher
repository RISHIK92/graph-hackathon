// name: current_in_chain
// purpose: one current assertion in a chain, the suggested correction for a stale span
// params: c
// indexes: Assertion.chain_id
// golden: tests/test_templates.py::test_goldens[current_in_chain]
MATCH (a:Assertion {chain_id:$c})
WHERE a.status = 'current'
RETURN a.id AS id, a.statement AS st LIMIT 1
