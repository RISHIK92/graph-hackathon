// name: span_view
// purpose: one span with every Source revision that supplied it (GET /spans/{id})
// params: id, max
// indexes: Span.id
// golden: tests/test_templates.py::test_goldens[span_view]
MATCH (s:Span {id:$id})<-[h:HAS_SPAN]-(src:Source)
RETURN s.text AS text, s.kind AS kind, s.ts AS ts, s.author_id AS author, s.author_role AS role,
       collect({source:src.id, title:src.title, uri:src.uri, cs:h.char_start, ce:h.char_end,
                latest:src.is_latest, live:h.removed_at = $max}) AS revisions
