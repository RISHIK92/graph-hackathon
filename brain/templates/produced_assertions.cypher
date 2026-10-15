// name: produced_assertions
// purpose: assertions an action produced
// params: id
// indexes: Action.id
// golden: tests/test_templates.py::test_goldens[produced_assertions]
MATCH (ac:Action {id:$id})-[:PRODUCED]->(x:Assertion)
RETURN x.id AS id
