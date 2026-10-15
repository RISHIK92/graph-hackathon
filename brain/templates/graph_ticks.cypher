// name: graph_ticks
// purpose: distinct valid_from times of projection edges, for the slider (GET /graph)
// params: none
// indexes: none (scans projection edges; bounded by the world size)
// golden: tests/test_templates.py::test_goldens[graph_ticks]
MATCH ()-[e]->() WHERE e.aid IS NOT NULL AND e.valid_from > 0
RETURN DISTINCT e.valid_from AS t ORDER BY t
