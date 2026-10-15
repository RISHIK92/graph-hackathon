// name: turn_span
// purpose: a span of the given session Source, with author role (learn_fact)
// params: id, src
// indexes: Source.id
// golden: tests/test_templates.py::test_goldens[turn_span]
MATCH (src:Source {id:$src})-[:HAS_SPAN]->(s:Span {id:$id})
RETURN s.text AS text, s.author_role AS role, s.ts AS ts
