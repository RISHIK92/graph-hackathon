// name: stale_detection
// purpose: latest-revision spans still stating a superseded or retracted fact, optionally about one entity ('' for all) (A45, A75)
// params: max, e
// indexes: Source.is_latest
// golden: tests/test_templates.py::test_goldens[stale_detection]
MATCH (src:Source)-[h:HAS_SPAN]->(s:Span)<-[e:EVIDENCED_BY]-(a:Assertion)
WHERE src.is_latest = true AND src.kind <> 'confirmation' AND src.kind <> 'draft'
  AND h.removed_at = $max AND e.removed_at = $max AND e.authority >= 1
  AND (a.status = 'superseded' OR a.status = 'retracted') AND a.valid_to > src.updated_at
  AND ($e = '' OR a.subject_id = $e OR a.object_id = $e)
RETURN DISTINCT s.id AS span, src.id AS source, src.doc_key AS doc_key, src.title AS title,
       a.id AS aid, a.statement AS statement, a.subject_id AS s, a.object_id AS o, a.predicate AS p,
       a.valid_to AS valid_to, a.chain_id AS chain, 'stale' AS why
