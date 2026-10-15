// name: dispute_chains
// purpose: chains with a live DISPUTES edge from a disputed assertion (open-dispute markers)
// params: max
// indexes: none (scans DISPUTES edges; there are few)
// golden: tests/test_templates.py::test_goldens[dispute_chains]
MATCH (d:Assertion)-[x:DISPUTES]->(m:Assertion) WHERE x.removed_at = $max AND d.status = 'disputed'
RETURN DISTINCT m.chain_id AS chain
