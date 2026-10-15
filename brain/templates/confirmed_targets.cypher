// name: confirmed_targets
// purpose: assertions an action added evidence to (undo of a confirmation)
// params: ac
// indexes: none (EVIDENCED_BY.action_id has no index; few actions add evidence)
// golden: tests/test_templates.py::test_goldens[confirmed_targets]
MATCH (a:Assertion)-[e:EVIDENCED_BY]->(:Span)
WHERE e.action_id = $ac
RETURN DISTINCT a.id AS id
