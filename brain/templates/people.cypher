// name: people
// purpose: every person with team, teams led and decisions at V (GET /people)
// params: V
// indexes: none (lists every Person)
// golden: tests/test_templates.py::test_goldens[people]
MATCH (p:Person)
OPTIONAL MATCH (p)-[m:MEMBER_OF]->(t:Team) WHERE m.primary = true AND m.valid_from <= $V AND m.valid_to > $V
WITH p, collect(t.name) AS team
OPTIONAL MATCH (p)-[l:LEADS]->(lt:Team) WHERE l.valid_from <= $V AND l.valid_to > $V
WITH p, team, collect(lt.name) AS leads
OPTIONAL MATCH (d:Decision)-[db:DECIDED_BY]->(p) WHERE db.valid_to > $V
RETURN p.id AS id, p.name AS name, p.title AS title, team, leads, collect(d.name) AS decides
ORDER BY name
