// name: belief_owners_of
// purpose: current owners of an entity with authority >= 2, for eligibility rules (A57)
// params: x, now
// indexes: Entity.id
// golden: tests/test_templates.py::test_goldens[belief_owners_of]
MATCH (o:Entity)-[r:OWNS]->(x:Entity {id:$x})
WHERE r.valid_from <= $now AND r.valid_to > $now AND r.authority >= 2
RETURN o.id AS owner, o.name AS name, r.aid AS aid
