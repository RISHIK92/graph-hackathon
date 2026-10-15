// name: decision_status
// purpose: a decision's status, status assertion and name (draft_adr_supersession)
// params: d
// indexes: Decision.id
// golden: tests/test_templates.py::test_goldens[decision_status]
MATCH (d:Decision {id:$d})
RETURN d.status AS s, d.status_aid AS aid, d.name AS n
