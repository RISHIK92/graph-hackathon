// name: decisions_affecting
// purpose: decisions that currently AFFECT a system or project, accepted first (trace_decision entry)
// params: x, V
// indexes: Entity.id, AFFECTS.valid_to
// golden: tests/test_templates.py::test_goldens[decisions_affecting]
MATCH (d:Decision)-[a:AFFECTS]->(x:Entity {id:$x})
WHERE a.valid_from <= $V AND a.valid_to > $V
RETURN d.id AS id, d.name AS name, d.title AS title, d.status AS status, a.aid AS aid
ORDER BY CASE d.status WHEN 'accepted' THEN 0 ELSE 1 END, d.decided_at DESC
