// name: belief_all_leads
// purpose: every current team lead with authority >= 2, for eligibility rules (A57)
// params: now
// indexes: none (scans LEADS edges; one per team)
// golden: tests/test_templates.py::test_goldens[belief_all_leads]
MATCH (p:Person)-[l:LEADS]->(t:Team)
WHERE l.valid_from <= $now AND l.valid_to > $now AND l.authority >= 2
RETURN p.id AS person, p.name AS name, t.id AS team, l.aid AS aid
