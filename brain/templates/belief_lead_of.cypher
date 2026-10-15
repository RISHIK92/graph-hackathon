// name: belief_lead_of
// purpose: current leads of a team with authority >= 2, for eligibility rules (A57)
// params: t, now
// indexes: Entity.id
// golden: tests/test_templates.py::test_goldens[belief_lead_of]
MATCH (p:Person)-[l:LEADS]->(t:Entity {id:$t})
WHERE l.valid_from <= $now AND l.valid_to > $now AND l.authority >= 2
RETURN p.id AS person, p.name AS name, l.aid AS aid
