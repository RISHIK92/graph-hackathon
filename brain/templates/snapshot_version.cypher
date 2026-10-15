// name: snapshot_version
// purpose: a fingerprint of the main graph's writes (assertions and actions); a snapshot graph is rebuilt when it changes (item 17)
// params: none
// indexes: none (counts every assertion and action; bounded by the world size)
// golden: tests/test_templates.py::test_goldens[snapshot_version]
MATCH (a:Assertion)
WITH count(a) AS n, max(a.recorded_at) AS last, max(a.retracted_at) AS gone
OPTIONAL MATCH (ac:Action)
RETURN n, last, gone, count(ac) AS actions
