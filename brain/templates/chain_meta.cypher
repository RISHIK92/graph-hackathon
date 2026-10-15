// name: chain_meta
// purpose: a chain's predicate, qualifier and key (ingest re-sync)
// params: c
// indexes: Chain.id
// golden: tests/test_templates.py::test_goldens[chain_meta]
MATCH (c:Chain {id:$c})
RETURN c.predicate AS p, c.qualifier AS q, c.key_id AS k
