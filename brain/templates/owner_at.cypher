// name: owner_at
// purpose: current-belief owner of x at valid time V via the OWNS projection (03 §1.2 get_owner step 1)
// params: x, V
// indexes: Entity.id, OWNS.valid_to (relationship range)
// golden: tests/test_templates.py::test_goldens[owner_at]
MATCH (owner:Entity)-[o:OWNS]->(x:Entity {id:$x})
WHERE o.valid_from <= $V AND o.valid_to > $V
RETURN owner.id AS owner, owner.name AS name, o.aid AS aid, o.valid_from AS vf, o.valid_to AS vt, o.authority AS authority
