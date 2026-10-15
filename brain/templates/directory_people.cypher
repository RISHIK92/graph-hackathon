// name: directory_people
// purpose: every person with primary team, teams led, decisions and ticket count at V (GET /directory)
// params: V
// indexes: none (lists every Person)
// golden: tests/test_templates.py::test_goldens[directory_people]
MATCH (p:Person)
OPTIONAL MATCH (p)-[m:MEMBER_OF]->(t:Team) WHERE m.primary = true AND m.valid_from <= $V AND m.valid_to > $V
WITH p, collect({id:t.id, name:t.name})[0] AS team
OPTIONAL MATCH (p)-[l:LEADS]->(lt:Team) WHERE l.valid_from <= $V AND l.valid_to > $V
WITH p, team, collect({id:lt.id, name:lt.name}) AS leads
OPTIONAL MATCH (d:Decision)-[db:DECIDED_BY]->(p) WHERE db.valid_from <= $V AND db.valid_to > $V
WITH p, team, leads, collect({id:d.id, name:d.name}) AS decides
OPTIONAL MATCH (k:Ticket)-[a:ASSIGNED_TO]->(p) WHERE a.valid_from <= $V AND a.valid_to > $V
RETURN p.id AS id, p.name AS name, p.title AS title, team, leads, decides, count(k) AS tickets
ORDER BY name
