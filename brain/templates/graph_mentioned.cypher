// name: graph_mentioned
// purpose: entities mentioned by spans of the given kinds (GET /graph source filter)
// params: k
// indexes: none (scans MENTIONS edges for the filter)
// golden: tests/test_templates.py::test_goldens[graph_mentioned]
MATCH (s:Span)-[:MENTIONS]->(n:Entity) WHERE s.kind IN $k
RETURN DISTINCT n.id AS id
