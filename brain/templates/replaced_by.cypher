// name: replaced_by
// purpose: decisions that replace d (incoming REPLACES projection), for discovery (A55)
// params: d, V
// indexes: Entity.id
// golden: tests/test_templates.py::test_goldens[replaced_by]
MATCH (n:Decision)-[r:REPLACES]->(d:Decision {id:$d})
WHERE r.valid_from <= $V AND r.valid_to > $V
RETURN n.id AS id, r.aid AS aid
