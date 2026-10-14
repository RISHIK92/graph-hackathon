// name: proposal_links
// purpose: for proposals: the producing Action and any CONFIRMS from a non-retracted assertion (A39, A55)
// params: ids, now
// indexes: Assertion.id
// golden: tests/test_templates.py::test_goldens[proposal_links]
UNWIND $ids AS i
MATCH (p:Assertion {id:i})
OPTIONAL MATCH (ac:Action)-[:PRODUCED]->(p)
WITH p, collect(ac.id) AS producers
OPTIONAL MATCH (c:Assertion)-[:CONFIRMS]->(p) WHERE c.retracted_at > $now
RETURN p.id AS id, producers, collect(c.id) AS confirmed_by
