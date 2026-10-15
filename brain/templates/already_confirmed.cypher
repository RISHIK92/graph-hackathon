// name: already_confirmed
// purpose: a non-retracted assertion confirming a proposal, and the action that produced it
// params: id, now
// indexes: Assertion.id
// golden: tests/test_templates.py::test_goldens[already_confirmed]
// Anchored on the proposal first: as one pattern 4.22.0 starts from an Assertion label scan on c.
MATCH (p:Assertion {id:$id})
WITH p
MATCH (c:Assertion)-[:CONFIRMS]->(p)
WHERE c.retracted_at > $now
OPTIONAL MATCH (ac:Action)-[:PRODUCED]->(c)
RETURN c.id AS c, ac.id AS ac
