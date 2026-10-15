// name: pending_proposals
// purpose: every done action with an unconfirmed proposal, with its actor (GET /people/{id}/pending)
// params: none
// indexes: none (lists open proposals; Action has no status index)
// golden: tests/test_templates.py::test_goldens[pending_proposals]
MATCH (ac:Action)-[:PRODUCED]->(p:Assertion) WHERE p.status = 'proposed' AND ac.status = 'done'
  AND NOT (p)<-[:CONFIRMS]-(:Assertion {status:'current'})
RETURN DISTINCT ac.id AS action_id, ac.kind AS kind, ac.summary AS summary, ac.actor AS actor
