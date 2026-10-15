// name: source_view
// purpose: one Source node with its spans and offsets (GET /sources/{id})
// params: id
// indexes: Source.id
// golden: tests/test_templates.py::test_goldens[source_view]
MATCH (s:Source {id:$id})
OPTIONAL MATCH (s)-[h:HAS_SPAN]->(sp:Span)
RETURN s AS source, collect({span:sp.id, text:sp.text, cs:h.char_start, ce:h.char_end, ord:h.ordinal}) AS spans
