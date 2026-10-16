// name: stale_override
// purpose: latest-revision spans whose fact supersedes a run with live confirmation evidence (A45, A75)
// params: max
// indexes: Assertion.run_id
// golden: tests/test_templates.py::test_goldens[stale_override]
// Anchored on the live SUPERSEDES edges, and the run lookup projects `old.run_id` through WITH first: with
// `MATCH (m:Assertion {run_id: old.run_id})` 6.0.1 skips the run_id index and walks every EVIDENCED_BY edge
// for each row (F27; 750 ms at 10x scale, against 30 ms on 4.22.0).
MATCH (a:Assertion)-[sp:SUPERSEDES]->(old:Assertion)
WHERE sp.removed_at = $max
WITH a, old.run_id AS rid
MATCH (m:Assertion) WHERE m.run_id = rid
WITH a, m
MATCH (m)-[ce:EVIDENCED_BY]->(:Span)
WHERE ce.form = 'confirmation' AND ce.removed_at > a.recorded_at
WITH DISTINCT a
MATCH (src:Source)-[h:HAS_SPAN]->(s:Span)<-[e:EVIDENCED_BY]-(a)
WHERE src.is_latest = true AND h.removed_at = $max AND e.removed_at = $max
  AND src.kind <> 'confirmation' AND src.kind <> 'draft'
RETURN DISTINCT s.id AS span, src.id AS source, src.doc_key AS doc_key, src.title AS title,
       a.id AS aid, a.statement AS statement, a.subject_id AS s, a.object_id AS o, a.predicate AS p,
       a.valid_to AS valid_to, a.chain_id AS chain, 'overrides a confirmation' AS why
