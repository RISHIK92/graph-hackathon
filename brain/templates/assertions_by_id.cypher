// name: assertions_by_id
// purpose: stored assertion fields (current belief) for pack facts
// params: ids
// indexes: Assertion.id
// golden: tests/test_templates.py::test_goldens[assertions_by_id]
UNWIND $ids AS i
MATCH (a:Assertion {id:i})
RETURN a.id AS assertion_id, a.run_id AS run_id, a.predicate AS predicate, a.qualifier AS qualifier,
       a.subject_id AS subject_id, a.object_id AS object_id, a.object_value AS object_value, a.negated AS negated,
       a.valid_from AS valid_from, a.valid_to AS valid_to, a.status AS status, a.authority AS authority,
       a.statement AS statement, a.chain_id AS chain_id, a.recorded_at AS recorded_at, a.retracted_at AS retracted_at
