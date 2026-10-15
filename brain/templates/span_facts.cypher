// name: span_facts
// purpose: the stored status of each fact a quoted span evidences, to flag outdated quotes (M6)
// params: sids (list of span ids), max
// indexes: Span.id
// golden: tests/test_templates.py::test_goldens[span_facts]
// Anchored through WITH: as two MATCH clauses, 6.0.1 planned a Span label scan and dropped `s.id IN $sids`,
// returning the facts of every span (F24).
MATCH (s:Span) WHERE s.id IN $sids
WITH s
MATCH (a:Assertion)-[e:EVIDENCED_BY]->(s)
WHERE e.removed_at = $max
RETURN s.id AS span, a.statement AS statement, a.status AS status, a.valid_to AS valid_to
