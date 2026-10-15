// name: doc_evidence
// purpose: non-confirmation, non-action evidence from every revision of a document (ingest step 9)
// params: k
// indexes: Source.doc_key
// golden: tests/test_templates.py::test_goldens[doc_evidence]
MATCH (src:Source {doc_key:$k})-[:HAS_SPAN]->(sp:Span)<-[e:EVIDENCED_BY]-(a:Assertion)
WHERE e.form <> 'confirmation' AND e.action_id = ''
WITH DISTINCT sp, a, e
RETURN sp.id AS span, a.id AS aid, a.chain_id AS chain, e.removed_at AS rm, e.replaced_by AS rb
