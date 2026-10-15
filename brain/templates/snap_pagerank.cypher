// name: snap_pagerank
// purpose: PageRank of systems over DEPENDS_ON in a snapshot graph: the most depended-on systems, directly or indirectly (critical_systems, item 17)
// params: none
// indexes: none (an algorithm over the whole snapshot graph)
// golden: tests/test_templates.py::test_goldens[snap_pagerank]
CALL algo.pageRank('System', 'DEPENDS_ON') YIELD node, score
RETURN node.id AS id, node.name AS name, score
