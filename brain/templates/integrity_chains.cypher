// name: integrity_chains
// purpose: every chain's predicate, qualifier and key (deep integrity, projection rebuild)
// params: none
// indexes: none (an integrity sweep over every chain)
// golden: tests/test_templates.py::test_goldens[integrity_chains]
MATCH (c:Chain)
RETURN c.id AS id, c.predicate AS p, c.qualifier AS q, c.key_id AS k
