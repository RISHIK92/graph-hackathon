// name: directory_tickets
// purpose: every ticket with what it is about, its assignee and current state at V (GET /directory)
// params: V
// indexes: none (lists every Ticket)
// golden: tests/test_templates.py::test_goldens[directory_tickets]
MATCH (k:Ticket)
OPTIONAL MATCH (k)-[ab:ABOUT]->(x:Entity) WHERE ab.valid_from <= $V AND ab.valid_to > $V
WITH k, collect({id:x.id, name:x.name})[0] AS about
OPTIONAL MATCH (k)-[a:ASSIGNED_TO]->(p:Person) WHERE a.valid_from <= $V AND a.valid_to > $V
WITH k, about, collect({id:p.id, name:p.name, aid:a.aid})[0] AS assignee
OPTIONAL MATCH (st:Assertion {subject_id:k.id, predicate:'HAS_STATE'})
WHERE st.status = 'current' AND st.valid_from <= $V AND st.valid_to > $V
RETURN k.id AS id, k.name AS name, k.description AS description, about, assignee,
       collect(st.object_value)[0] AS state ORDER BY name
