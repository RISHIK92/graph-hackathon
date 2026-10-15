// name: demo_identity
// purpose: the demo identity stored on the world_meta Source, if any (API default acting-as)
// params: none
// indexes: none (one world_meta Source per graph; Source has no kind index)
// golden: tests/test_templates.py::test_goldens[demo_identity]
MATCH (s:Source {kind:'world_meta'})
RETURN s.demo_identity AS d LIMIT 1
