// name: revisions
// purpose: every revision Source of one document
// params: k
// indexes: Source.doc_key
// golden: tests/test_templates.py::test_goldens[revisions]
MATCH (s:Source {doc_key:$k})
RETURN s.id AS id, s.updated_at AS updated_at, s.is_latest AS is_latest, s.ingested_at AS ingested_at, s.status AS status
