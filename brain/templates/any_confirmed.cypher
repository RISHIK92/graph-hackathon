// name: any_confirmed
// purpose: whether any non-retracted assertion confirms a proposal an action produced
// params: id, now
// indexes: Action.id
// golden: tests/test_templates.py::test_goldens[any_confirmed]
MATCH (ac:Action {id:$id})-[:PRODUCED]->(p:Assertion)<-[:CONFIRMS]-(c:Assertion)
WHERE c.retracted_at > $now
RETURN c.id AS c LIMIT 1
