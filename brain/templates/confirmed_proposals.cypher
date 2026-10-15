// name: confirmed_proposals
// purpose: proposals confirmed by the assertions an action produced
// params: ac
// indexes: Action.id
// golden: tests/test_templates.py::test_goldens[confirmed_proposals]
MATCH (ac:Action {id:$ac})-[:PRODUCED]->(n:Assertion)-[:CONFIRMS]->(p:Assertion)
RETURN p.id AS id
