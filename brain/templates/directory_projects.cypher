// name: directory_projects
// purpose: every project with owner, systems and people count at V (GET /directory)
// params: V
// indexes: none (lists every Project)
// golden: tests/test_templates.py::test_goldens[directory_projects]
MATCH (p:Project)
OPTIONAL MATCH (t:Team)-[o:OWNS]->(p) WHERE o.valid_from <= $V AND o.valid_to > $V
WITH p, collect({id:t.id, name:t.name, aid:o.aid})[0] AS owner
OPTIONAL MATCH (s:System)-[pp:PART_OF]->(p) WHERE pp.valid_from <= $V AND pp.valid_to > $V
WITH p, owner, collect({id:s.id, name:s.name}) AS systems
OPTIONAL MATCH (w:Person)-[wo:WORKS_ON]->(p) WHERE wo.valid_from <= $V AND wo.valid_to > $V
RETURN p.id AS id, p.name AS name, p.description AS description, owner, systems, count(w) AS people
ORDER BY name
