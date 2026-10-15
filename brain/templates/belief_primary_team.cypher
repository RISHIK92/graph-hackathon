// name: belief_primary_team
// purpose: a person's current primary team with authority >= 2, for eligibility rules (A57)
// params: p, now
// indexes: Person.id
// golden: tests/test_templates.py::test_goldens[belief_primary_team]
MATCH (p:Person {id:$p})-[r:MEMBER_OF]->(t:Team)
WHERE r.primary = true AND r.valid_from <= $now AND r.valid_to > $now AND r.authority >= 2
RETURN t.id AS team, r.aid AS aid
