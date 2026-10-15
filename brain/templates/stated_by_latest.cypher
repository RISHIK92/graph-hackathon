// name: stated_by_latest
// purpose: chains and assertions the latest revision of a document states through its spans (ingest step 9)
// params: s
// indexes: Source.id
// golden: tests/test_templates.py::test_goldens[stated_by_latest]
MATCH (src:Source {id:$s})-[:HAS_SPAN]->(sp:Span)<-[:EVIDENCED_BY]-(a:Assertion)
RETURN DISTINCT a.chain_id AS chain, a.id AS aid
