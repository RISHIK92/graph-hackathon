// name: existing_spans
// purpose: which of the given span ids exist, with their timestamps (ingestion dedup)
// params: ids
// indexes: Span.id
// golden: tests/test_templates.py::test_goldens[existing_spans]
// `s.id IN $ids`, not UNWIND + {id:i}: 6.0.1 skips the index for the UNWIND form (see span_details).
MATCH (s:Span)
WHERE s.id IN $ids
RETURN s.id AS id, s.ts AS ts
