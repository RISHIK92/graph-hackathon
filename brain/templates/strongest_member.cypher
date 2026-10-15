// name: strongest_member
// purpose: a run's current member with the highest authority, for the guard (A57)
// params: r
// indexes: Assertion.run_id
// golden: tests/test_templates.py::test_goldens[strongest_member]
MATCH (a:Assertion {run_id:$r})
WHERE a.status = 'current'
RETURN a.id AS id, a.authority AS au ORDER BY au DESC LIMIT 1
