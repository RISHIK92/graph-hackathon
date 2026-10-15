// name: overview_pending
// purpose: done proposal actions whose proposal no current assertion confirms (GET /overview)
// params: none
// indexes: none (lists open proposals; Action has no kind index)
// golden: tests/test_templates.py::test_goldens[overview_pending]
MATCH (ac:Action) WHERE ac.kind IN ['draft_adr_supersession','route_to_owner'] AND ac.status = 'done'
MATCH (ac)-[:PRODUCED]->(p:Assertion) WHERE p.status = 'proposed'
  AND NOT (p)<-[:CONFIRMS]-(:Assertion {status:'current'})
RETURN DISTINCT ac.id AS action_id, ac.kind AS kind, ac.summary AS summary
