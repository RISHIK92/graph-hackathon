// name: action_targets
// purpose: entities an action targets
// params: id
// indexes: Action.id
// golden: tests/test_templates.py::test_goldens[action_targets]
MATCH (ac:Action {id:$id})-[:TARGETS]->(e:Entity)
RETURN e.id AS id
