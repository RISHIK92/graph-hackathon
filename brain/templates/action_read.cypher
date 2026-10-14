// name: action_read
// purpose: an Action with what it relied on and produced (explain_action, action view)
// params: id
// indexes: Action.id
// golden: tests/test_templates.py::test_goldens[action_read]
MATCH (ac:Action {id:$id})
OPTIONAL MATCH (ac)-[:BASED_ON]->(b:Assertion)
WITH ac, collect(DISTINCT b.id) AS based_on
OPTIONAL MATCH (ac)-[:PRODUCED]->(pa:Assertion)
WITH ac, based_on, collect(DISTINCT pa.id) AS produced
OPTIONAL MATCH (ac)-[:PRODUCED]->(ps:Source)
WITH ac, based_on, produced, collect(DISTINCT ps.id) AS sources
OPTIONAL MATCH (ac)-[:TARGETS]->(t:Entity)
RETURN ac AS action, based_on, produced, sources, collect(DISTINCT t.id) AS targets
