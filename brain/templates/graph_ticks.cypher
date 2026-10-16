// name: graph_ticks
// purpose: distinct valid_from times of projection edges with how many edges start then, for the slider and its markers (GET /graph)
// params: none
// indexes: none (scans the entities' out-edges; bounded by the world size)
// golden: tests/test_templates.py::test_goldens[graph_ticks]
// Projection edges join two entities. Anchoring on :Entity at both ends walks only their out-edges; the old
// `MATCH ()-[e]->()` walked every edge in the graph (spans, evidence, chains): 98 ms vs 6 ms at 10x on 6.0.1.
MATCH (:Entity)-[e]->(:Entity) WHERE e.aid IS NOT NULL AND e.valid_from > 0
RETURN e.valid_from AS t, count(e) AS n ORDER BY t
