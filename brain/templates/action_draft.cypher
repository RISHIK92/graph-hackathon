// name: action_draft
// purpose: the draft Source an action produced, if any (GET /actions/{id})
// params: id
// indexes: Action.id
// golden: tests/test_templates.py::test_goldens[action_draft]
MATCH (ac:Action {id:$id})-[:PRODUCED]->(s:Source {kind:'draft'})
RETURN s.id AS id
