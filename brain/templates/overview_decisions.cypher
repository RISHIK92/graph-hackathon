// name: overview_decisions
// purpose: accepted decisions with what they affect at V (GET /overview)
// params: V
// indexes: none (lists every accepted Decision)
// golden: tests/test_templates.py::test_goldens[overview_decisions]
MATCH (d:Decision) WHERE d.status = 'accepted'
OPTIONAL MATCH (d)-[a:AFFECTS]->(x:Entity) WHERE a.valid_from <= $V AND a.valid_to > $V
RETURN d.id AS id, d.name AS name, d.title AS title, d.status_aid AS aid,
       collect({id:x.id, name:x.name, aid:a.aid}) AS affects ORDER BY name
