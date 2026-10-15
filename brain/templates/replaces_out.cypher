// name: replaces_out
// purpose: decisions a decision replaces, at V (trace_decision)
// params: d, V
// indexes: Decision.id
// golden: tests/test_templates.py::test_goldens[replaces_out]
MATCH (d:Decision {id:$d})-[r:REPLACES]->(o:Decision)
WHERE r.valid_to > $V
RETURN o.id AS o, r.aid AS aid
