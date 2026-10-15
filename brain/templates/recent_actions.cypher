// name: recent_actions
// purpose: a user's 10 most recent actions, by client or actor (memory reads)
// params: u
// indexes: none (Action has no client or actor index; bounded by LIMIT 10)
// golden: tests/test_templates.py::test_goldens[recent_actions]
MATCH (ac:Action)
WHERE ac.client = $u OR ac.actor = $u
RETURN ac.id AS id
ORDER BY ac.recorded_at DESC LIMIT 10
