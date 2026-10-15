// name: snap_leaders
// purpose: every current LEADS edge in a snapshot graph, with the led team (knowledge_gaps, item 17)
// params: none
// indexes: none (every LEADS edge; one per team)
// golden: tests/test_templates.py::test_goldens[snap_leaders]
MATCH (p:Person)-[e:LEADS]->(t:Team)
RETURN p.id AS person, t.id AS team, e.aid AS aid
