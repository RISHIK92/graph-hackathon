// name: confirms_of
// purpose: confirmations of the given proposals, with status and producing action (explain_action then/now)
// params: ids
// indexes: Assertion.id
// golden: tests/test_templates.py::test_goldens[confirms_of]
// Anchored on the proposals first, like already_confirmed.
MATCH (p:Assertion)
WHERE p.id IN $ids
WITH p
MATCH (c:Assertion)-[:CONFIRMS]->(p)
OPTIONAL MATCH (ac:Action)-[:PRODUCED]->(c)
RETURN p.id AS proposal, c.id AS confirmed, c.status AS status, ac.id AS action
