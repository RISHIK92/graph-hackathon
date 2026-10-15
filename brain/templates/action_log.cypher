// name: action_log
// purpose: a person's 50 most recent actions (GET /people/{id}/pending)
// params: p
// indexes: none (Action has no actor index; bounded by LIMIT 50)
// golden: tests/test_templates.py::test_goldens[action_log]
MATCH (ac:Action {actor:$p})
RETURN ac.id AS id, ac.kind AS kind, ac.status AS status, ac.summary AS summary, ac.recorded_at AS at
ORDER BY at DESC LIMIT 50
