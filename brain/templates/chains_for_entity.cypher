// name: chains_for_entity
// purpose: chain ids for an entity and predicate (get_history)
// params: e, p
// indexes: Assertion.subject_id, Assertion.object_id
// golden: tests/test_templates.py::test_goldens[chains_for_entity]
MATCH (a:Assertion {subject_id:$e}) WHERE a.predicate = $p
RETURN DISTINCT a.chain_id AS chain, a.qualifier AS q
UNION
MATCH (a:Assertion {object_id:$e}) WHERE a.predicate = $p
RETURN DISTINCT a.chain_id AS chain, a.qualifier AS q
