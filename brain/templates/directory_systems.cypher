// name: directory_systems
// purpose: every system with owner, project, dependency counts and decision count at V (GET /directory)
// params: V
// indexes: none (lists every System)
// golden: tests/test_templates.py::test_goldens[directory_systems]
MATCH (s:System)
OPTIONAL MATCH (t:Team)-[o:OWNS]->(s) WHERE o.valid_from <= $V AND o.valid_to > $V
WITH s, collect({id:t.id, name:t.name, aid:o.aid})[0] AS owner
OPTIONAL MATCH (s)-[d:DEPENDS_ON]->(:Entity) WHERE d.valid_from <= $V AND d.valid_to > $V
WITH s, owner, count(d) AS depends_on
OPTIONAL MATCH (:Entity)-[u:DEPENDS_ON]->(s) WHERE u.valid_from <= $V AND u.valid_to > $V
WITH s, owner, depends_on, count(u) AS depended_on_by
OPTIONAL MATCH (s)-[pp:PART_OF]->(pr:Project) WHERE pp.valid_from <= $V AND pp.valid_to > $V
WITH s, owner, depends_on, depended_on_by, collect({id:pr.id, name:pr.name})[0] AS project
OPTIONAL MATCH (dc:Decision)-[af:AFFECTS]->(s) WHERE af.valid_from <= $V AND af.valid_to > $V
RETURN s.id AS id, s.name AS name, s.description AS description, owner, project,
       depends_on, depended_on_by, count(dc) AS decisions ORDER BY name
