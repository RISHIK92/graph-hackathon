// name: latest_spans
// purpose: span ids of one Source revision (ingest step 9)
// params: l
// indexes: Source.id
// golden: tests/test_templates.py::test_goldens[latest_spans]
MATCH (src:Source {id:$l})-[:HAS_SPAN]->(sp:Span)
RETURN sp.id AS id
