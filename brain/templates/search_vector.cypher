// name: search_vector
// purpose: semantic span entry; distance ascending; filters after YIELD (R6)
// params: k, vec
// indexes: vector Span.embedding
// golden: tests/test_templates.py::test_goldens[search_vector]
CALL db.idx.vector.queryNodes('Span', 'embedding', $k, vecf32($vec)) YIELD node, score
WHERE node.kind <> 'draft' AND node.author_role <> 'agent'
RETURN node.id AS id, node.ts AS ts, node.kind AS kind, score
ORDER BY score ASC
