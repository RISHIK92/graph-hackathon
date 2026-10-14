// name: owner_previous
// purpose: latest closed OWNS run when nothing is current (get_owner step 5)
// params: x, V
// indexes: Entity.id, OWNS.valid_to
// golden: tests/test_templates.py::test_goldens[owner_previous]
MATCH (owner:Entity)-[o:OWNS]->(x:Entity {id:$x})
WHERE o.valid_to <= $V
RETURN owner.id AS owner, owner.name AS name, o.aid AS aid, o.valid_from AS vf, o.valid_to AS vt, o.authority AS authority
ORDER BY o.valid_to DESC LIMIT 1
