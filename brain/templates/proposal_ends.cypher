// name: proposal_ends
// purpose: a proposal's subject and object ids (trace_decision follows draft decisions)
// params: p
// indexes: Assertion.id
// golden: tests/test_templates.py::test_goldens[proposal_ends]
MATCH (a:Assertion {id:$p})
RETURN a.subject_id AS s, a.object_id AS o
