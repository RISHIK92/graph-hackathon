// name: snap_meta
// purpose: which main-graph version and valid time a snapshot graph was built from (item 17)
// params: none
// indexes: none (one Meta node per snapshot graph)
// golden: tests/test_templates.py::test_goldens[snap_meta]
MATCH (m:Meta)
RETURN m.version AS version, m.V AS V, m.built_at AS built_at
