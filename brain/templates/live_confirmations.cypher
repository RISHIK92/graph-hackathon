// name: live_confirmations
// purpose: confirmation evidence live at now on a run's members (02 §8 admissibility)
// params: run, now
// indexes: Assertion.run_id
// golden: tests/test_templates.py::test_goldens[live_confirmations]
MATCH (m:Assertion {run_id:$run})-[e:EVIDENCED_BY]->(s:Span)
WHERE e.form = 'confirmation' AND e.recorded_at <= $now AND e.removed_at > $now
RETURN m.id AS member, s.ts AS ts, e.action_id AS action_id
