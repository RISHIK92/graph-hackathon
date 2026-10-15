// name: disputed_run
// purpose: the run a disputed assertion's live DISPUTES edge points at
// params: id, max
// indexes: Assertion.id
// golden: tests/test_templates.py::test_goldens[disputed_run]
MATCH (a:Assertion {id:$id})-[d:DISPUTES]->(m:Assertion)
WHERE d.removed_at = $max
RETURN m.run_id AS run
