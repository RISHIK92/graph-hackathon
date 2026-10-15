// name: stale_override
// purpose: latest-revision spans whose fact supersedes a run with live confirmation evidence (A45, A75)
// params: max
// indexes: Source.is_latest
// golden: tests/test_templates.py::test_goldens[stale_override]
MATCH (src:Source)-[h:HAS_SPAN]->(s:Span)<-[e:EVIDENCED_BY]-(a:Assertion)-[sp:SUPERSEDES]->(old:Assertion)
WHERE src.is_latest = true AND h.removed_at = $max AND e.removed_at = $max AND sp.removed_at = $max
  AND src.kind <> 'confirmation' AND src.kind <> 'draft'
WITH s, src, a, old
MATCH (m:Assertion {run_id: old.run_id})-[ce:EVIDENCED_BY]->(:Span)
WHERE ce.form = 'confirmation' AND ce.removed_at > a.recorded_at
RETURN DISTINCT s.id AS span, src.id AS source, src.doc_key AS doc_key, src.title AS title,
       a.id AS aid, a.statement AS statement, a.subject_id AS s, a.object_id AS o, a.predicate AS p,
       a.valid_to AS valid_to, a.chain_id AS chain, 'overrides a confirmation' AS why
