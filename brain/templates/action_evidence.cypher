// name: action_evidence
// purpose: live evidence an action added to existing assertions (undo, A62)
// params: ac, max
// indexes: none (EVIDENCED_BY.action_id has no index; few actions add evidence)
// golden: tests/test_templates.py::test_goldens[action_evidence]
MATCH (a:Assertion)-[e:EVIDENCED_BY]->(s:Span)
WHERE e.action_id = $ac AND e.removed_at = $max
RETURN a.id AS aid, s.id AS sid
