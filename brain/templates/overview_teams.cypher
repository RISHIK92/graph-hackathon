// name: overview_teams
// purpose: every team with its lead, primary members and owned entities at V (GET /overview)
// params: V
// indexes: none (lists every Team; bounded by the world's team count)
// golden: tests/test_templates.py::test_goldens[overview_teams]
MATCH (t:Team)
OPTIONAL MATCH (p:Person)-[l:LEADS]->(t) WHERE l.valid_from <= $V AND l.valid_to > $V
WITH t, collect({id:p.id, name:p.name, aid:l.aid}) AS leads
OPTIONAL MATCH (m:Person)-[mm:MEMBER_OF]->(t) WHERE mm.primary = true AND mm.valid_from <= $V AND mm.valid_to > $V
WITH t, leads, collect({id:m.id, name:m.name, aid:mm.aid}) AS members
OPTIONAL MATCH (t)-[o:OWNS]->(x:Entity) WHERE o.valid_from <= $V AND o.valid_to > $V
RETURN t.id AS id, t.name AS name, leads, members, collect({id:x.id, name:x.name, aid:o.aid}) AS owns
ORDER BY name
