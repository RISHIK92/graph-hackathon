// name: draft_decision
// purpose: decisions an action attached MOTIVATED_BY edges to (undo of a draft ADR)
// params: id
// indexes: none (MOTIVATED_BY.action_id has no index; few such edges)
// golden: tests/test_templates.py::test_goldens[draft_decision]
MATCH (d:Decision)-[m:MOTIVATED_BY]->()
WHERE m.action_id = $id
RETURN DISTINCT d.id AS d
