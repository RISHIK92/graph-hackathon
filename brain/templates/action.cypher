// name: action
// purpose: one Action node
// params: id
// indexes: Action.id
// golden: tests/test_templates.py::test_goldens[action]
MATCH (ac:Action {id:$id})
RETURN ac
