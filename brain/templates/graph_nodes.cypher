// name: graph_nodes
// purpose: every entity node (GET /graph)
// params: none
// indexes: none (the whole-graph view; bounded by the world size)
// golden: tests/test_templates.py::test_goldens[graph_nodes]
MATCH (n:Entity)
RETURN n.id AS id, n.name AS name, labels(n) AS labels
