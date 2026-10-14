// name: link_fulltext
// purpose: full-text entity linking over name, aliases_text, description (sanitised input, R7)
// params: q
// indexes: full-text Entity
// golden: tests/test_templates.py::test_goldens[link_fulltext]
CALL db.idx.fulltext.queryNodes('Entity', $q) YIELD node, score
RETURN node.id AS id, node.name AS name, labels(node) AS labels, score
LIMIT 20
