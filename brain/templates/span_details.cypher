// name: span_details
// purpose: span text and the Source that supplied it, plus liveness of its HAS_SPAN edges at T (01 §5)
// params: sids (list of span ids), T
// indexes: Span.id
// golden: tests/test_templates.py::test_goldens[span_details]
UNWIND $sids AS sid
MATCH (s:Span {id:sid})<-[h:HAS_SPAN]-(src:Source)
WITH s, src, h ORDER BY src.updated_at DESC
WITH s, collect({src:src.id, title:src.title, uri:src.uri, kind:src.kind, doc_key:src.doc_key,
                 cs:h.char_start, ce:h.char_end, live:(h.recorded_at <= $T AND h.removed_at > $T)}) AS revs
RETURN s.id AS id, s.text AS text, s.ts AS ts, s.kind AS kind, s.author_role AS role, revs
