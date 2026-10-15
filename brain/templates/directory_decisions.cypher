// name: directory_decisions
// purpose: every decision with affects, deciders and replacements at V (GET /directory)
// params: V
// indexes: none (lists every Decision)
// golden: tests/test_templates.py::test_goldens[directory_decisions]
MATCH (d:Decision)
OPTIONAL MATCH (d)-[a:AFFECTS]->(x:Entity) WHERE a.valid_from <= $V AND a.valid_to > $V
WITH d, collect({id:x.id, name:x.name, aid:a.aid}) AS affects
OPTIONAL MATCH (d)-[db:DECIDED_BY]->(w:Person) WHERE db.valid_from <= $V AND db.valid_to > $V
WITH d, affects, collect({id:w.id, name:w.name}) AS deciders
OPTIONAL MATCH (d)-[r:REPLACES]->(old:Decision)
WITH d, affects, deciders, collect({id:old.id, name:old.name}) AS replaces
OPTIONAL MATCH (new:Decision)-[r2:REPLACES]->(d)
RETURN d.id AS id, d.name AS name, d.title AS title, d.description AS description, d.status AS status,
       d.decided_at AS decided_at, affects, deciders, replaces, collect({id:new.id, name:new.name}) AS replaced_by
ORDER BY name
