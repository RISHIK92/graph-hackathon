// name: rationale_spans
// purpose: live non-draft MOTIVATED_BY spans of a decision (A55)
// params: d, max
// indexes: Decision.id
// golden: tests/test_templates.py::test_goldens[rationale_spans]
MATCH (d:Decision {id:$d})-[m:MOTIVATED_BY]->(s:Span)
WHERE m.removed_at = $max AND s.kind <> 'draft'
RETURN s.id AS id
