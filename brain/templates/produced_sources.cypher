// name: produced_sources
// purpose: sources (drafts, confirmations) an action produced
// params: id
// indexes: Action.id
// golden: tests/test_templates.py::test_goldens[produced_sources]
MATCH (ac:Action {id:$id})-[:PRODUCED]->(x:Source)
RETURN x.id AS id
