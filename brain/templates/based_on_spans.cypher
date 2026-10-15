// name: based_on_spans
// purpose: non-draft spans behind the live rank >= 1 evidence of the given runs (A55)
// params: runs, max
// indexes: Assertion.run_id
// golden: tests/test_templates.py::test_goldens[based_on_spans]
// `run_id IN $runs`, not UNWIND + {run_id:r}: 6.0.1 skips the index for the UNWIND form (see span_details).
// Anchored first: as one pattern 6.0.1 starts from a Span label scan because of the s.kind filter.
MATCH (a:Assertion)
WHERE a.run_id IN $runs
WITH a
MATCH (a)-[e:EVIDENCED_BY]->(s:Span)
WHERE e.authority >= 1 AND e.removed_at = $max AND s.kind <> 'draft'
RETURN DISTINCT s.id AS id
