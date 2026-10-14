// name: search_fulltext
// purpose: lexical span entry, identifiers through @keys (R7)
// params: q
// indexes: full-text Span(text, keys)
// golden: tests/test_templates.py::test_goldens[search_fulltext]
CALL db.idx.fulltext.queryNodes('Span', $q) YIELD node, score
WHERE node.kind <> 'draft' AND node.author_role <> 'agent'
RETURN node.id AS id, node.ts AS ts, node.kind AS kind, score
LIMIT 50
