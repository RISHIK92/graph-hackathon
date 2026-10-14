// name: proposals_about
// purpose: proposed assertions whose subject or object is the entity, with any CONFIRMS from a non-retracted assertion (A39, A55)
// params: e
// indexes: Assertion.subject_id, Assertion.object_id
// golden: tests/test_templates.py::test_goldens[proposals_about]
MATCH (p:Assertion {subject_id:$e}) WHERE p.status = 'proposed' OR (p.status = 'retracted' AND p.authority = 0)
RETURN p.id AS id
UNION
MATCH (p:Assertion {object_id:$e}) WHERE p.status = 'proposed' OR (p.status = 'retracted' AND p.authority = 0)
RETURN p.id AS id
