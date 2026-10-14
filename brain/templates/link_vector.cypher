// name: link_vector
// purpose: vector entity linking; score is a distance, ascending (R6); over-fetch then filter after YIELD
// params: k, vec
// indexes: vector Entity.embedding
// golden: tests/test_templates.py::test_goldens[link_vector]
CALL db.idx.vector.queryNodes('Entity', 'embedding', $k, vecf32($vec)) YIELD node, score
RETURN node.id AS id, node.name AS name, labels(node) AS labels, score
ORDER BY score ASC
