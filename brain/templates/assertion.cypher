// name: assertion
// purpose: one assertion's identity, chain and status fields
// params: id
// indexes: Assertion.id
// golden: tests/test_templates.py::test_goldens[assertion]
MATCH (a:Assertion {id:$id})
RETURN a.id AS id, a.predicate AS predicate, a.qualifier AS qualifier, a.subject_id AS subject_id,
       a.object_id AS object_id, a.object_value AS object_value, a.negated AS negated, a.valid_from AS valid_from,
       a.status AS status, a.run_id AS run_id, a.chain_id AS chain_id, a.statement AS statement,
       a.retracted_at AS retracted_at
