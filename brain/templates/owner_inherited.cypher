// name: owner_inherited
// purpose: inherited owner through the system's PART_OF project at V (get_owner step 4)
// params: x, V
// indexes: Entity.id, PART_OF.valid_to, OWNS.valid_to
// golden: tests/test_templates.py::test_goldens[owner_inherited]
MATCH (x:Entity {id:$x})-[pp:PART_OF]->(p:Entity)
WHERE pp.valid_from <= $V AND pp.valid_to > $V
WITH p, pp
MATCH (owner:Entity)-[o:OWNS]->(p)
WHERE o.valid_from <= $V AND o.valid_to > $V
RETURN owner.id AS owner, owner.name AS name, o.aid AS aid, o.valid_from AS vf, o.valid_to AS vt,
       o.authority AS authority, p.id AS via, p.name AS via_name, pp.aid AS via_aid
