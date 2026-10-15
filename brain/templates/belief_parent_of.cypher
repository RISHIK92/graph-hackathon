// name: belief_parent_of
// purpose: the current PART_OF parent of an entity with authority >= 2, for eligibility rules (A57)
// params: x, now
// indexes: Entity.id
// golden: tests/test_templates.py::test_goldens[belief_parent_of]
MATCH (x:Entity {id:$x})-[r:PART_OF]->(p:Entity)
WHERE r.valid_from <= $now AND r.valid_to > $now AND r.authority >= 2
RETURN p.id AS parent, r.aid AS aid
