// name: turn_count
// purpose: the number of turns stored in a chat session
// params: s
// indexes: Source.id
// golden: tests/test_templates.py::test_goldens[turn_count]
MATCH (src:Source {id:$s})-[:HAS_SPAN]->(x:Span)
RETURN count(x) AS n
