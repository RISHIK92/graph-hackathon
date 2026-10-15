// name: proposal_links
// purpose: for proposals: the producing Action and any CONFIRMS from a non-retracted assertion (A39, A55)
// params: ids, now
// indexes: Assertion.id
// golden: tests/test_templates.py::test_goldens[proposal_links]
UNWIND $ids AS i
MATCH (p:Assertion {id:i})
// Comprehensions, one per WITH (R12): on 6.0.1 an OPTIONAL MATCH after the WITH collect() boundary
// returned no CONFIRMS rows (F21 family). A confirmation counts only once recorded at $now (as-of reads).
WITH p, [(ac:Action)-[:PRODUCED]->(p) | ac.id] AS producers
WITH p, producers, [(c:Assertion)-[:CONFIRMS]->(p) WHERE c.recorded_at <= $now AND c.retracted_at > $now | c.id] AS confirmed_by
RETURN p.id AS id, producers, confirmed_by
