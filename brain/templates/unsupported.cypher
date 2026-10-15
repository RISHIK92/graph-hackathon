// name: unsupported
// purpose: non-retracted extracted assertions with no live evidence left, to retract at the end of a run (A14a)
// params: max
// indexes: none (an end-of-run sweep over every assertion)
// golden: tests/test_templates.py::test_goldens[unsupported]
MATCH (a:Assertion)
WHERE a.retracted_at = $max AND a.extractor <> 'confirm_fact' AND NOT a.extractor STARTS WITH 'draft'
WITH a, [(a)-[e:EVIDENCED_BY]->() WHERE e.removed_at = $max | e] AS live
WITH a WHERE size(live) = 0
RETURN a.id AS aid
