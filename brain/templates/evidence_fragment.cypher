// name: evidence_fragment
// purpose: THE single access path to EVIDENCED_BY (03 §1.1, A29a, A59, A61). Drops rank 0, draft and agent spans, and evidence not live at T.
// params: aids (list of assertion ids), T (belief time)
// indexes: Assertion.id
// golden: tests/test_templates.py::test_goldens[evidence_fragment]
UNWIND $aids AS aid
MATCH (a:Assertion {id:aid})
WITH a, [(a)-[ev:EVIDENCED_BY]->(s) WHERE ev.authority >= 1 AND ev.recorded_at <= $T AND ev.removed_at > $T
          AND s.kind <> 'draft' AND s.author_role <> 'agent'
          | {span:s.id, form:ev.form, authority:ev.authority, qs:ev.quote_start, qe:ev.quote_end, src:ev.source_id}] AS evs
RETURN a.id AS aid, evs
