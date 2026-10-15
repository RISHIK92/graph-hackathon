// name: integrity_sentinel
// purpose: the number of GuardFail nodes; exactly one, the sentinel, is healthy (A51)
// params: none
// indexes: none (counts every GuardFail node; there should be one)
// golden: tests/test_templates.py::test_goldens[integrity_sentinel]
MATCH (s:GuardFail)
RETURN count(s) AS n
