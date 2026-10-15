// name: integrity_i11
// purpose: chains over the 50-assertion cap (I11)
// params: none
// indexes: none (an integrity sweep over every assertion)
// golden: tests/test_templates.py::test_goldens[integrity_i11]
MATCH (a:Assertion)
WITH a.chain_id AS c, count(a) AS n
WHERE n > 50
RETURN c, n
