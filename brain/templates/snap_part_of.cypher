// name: snap_part_of
// purpose: every current PART_OF edge in a snapshot graph, so a system can inherit its project's owner (knowledge_gaps, item 17)
// params: none
// indexes: none (every PART_OF edge; one per part)
// golden: tests/test_templates.py::test_goldens[snap_part_of]
MATCH (s:N)-[e:PART_OF]->(p:N)
RETURN s.id AS id, p.id AS project, e.aid AS aid
