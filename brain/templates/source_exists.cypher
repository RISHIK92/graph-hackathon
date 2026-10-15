// name: source_exists
// purpose: whether a Source exists, with its ingest time and latest flag
// params: id
// indexes: Source.id
// golden: tests/test_templates.py::test_goldens[source_exists]
MATCH (s:Source {id:$id})
RETURN s.ingested_at AS ingested_at, s.is_latest AS is_latest
