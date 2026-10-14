// name: lead_at
// purpose: the lead of a Team (or Project) at V (get_owner step 2; confirmer rule team_lead)
// params: t, V
// indexes: Entity.id, LEADS.valid_to
// golden: tests/test_templates.py::test_goldens[lead_at]
MATCH (p:Entity)-[l:LEADS]->(t:Entity {id:$t})
WHERE l.valid_from <= $V AND l.valid_to > $V
RETURN p.id AS lead, p.name AS name, l.aid AS aid, l.valid_from AS vf, l.valid_to AS vt, l.authority AS authority
