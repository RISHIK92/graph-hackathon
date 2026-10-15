// name: graph_edge_kinds
// purpose: source kinds of the live rank >= 1 evidence behind each edge's run (GET /graph filters)
// params: aids, max
// indexes: Assertion.run_id
// golden: tests/test_templates.py::test_goldens[graph_edge_kinds]
// `run_id IN $aids`, not UNWIND + {run_id:r}: 6.0.1 skips the index for the UNWIND form (see span_details).
MATCH (a:Assertion)-[ev:EVIDENCED_BY]->(s:Span)
WHERE a.run_id IN $aids AND ev.authority >= 1 AND ev.removed_at = $max
RETURN a.run_id AS aid, collect(DISTINCT s.kind) AS kinds
