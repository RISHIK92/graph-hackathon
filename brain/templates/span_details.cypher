// name: span_details
// purpose: span text and the Source that supplied it, plus liveness of its HAS_SPAN edges at T (01 §5)
// params: sids (list of span ids), T
// indexes: Span.id
// golden: tests/test_templates.py::test_goldens[span_details]
// `s.id IN $sids`, not UNWIND + {id:sid}: 6.0.1 plans the UNWIND form as a traverse off the Unwind
// with no Span.id index scan; the IN form uses the index on both versions.
MATCH (s:Span)<-[h:HAS_SPAN]-(src:Source) WHERE s.id IN $sids
WITH s, src, h ORDER BY src.updated_at DESC
WITH s, collect({src:src.id, title:src.title, uri:src.uri, kind:src.kind, doc_key:src.doc_key, system:src.system,
                 cs:h.char_start, ce:h.char_end, live:(h.recorded_at <= $T AND h.removed_at > $T)}) AS revs
RETURN s.id AS id, s.text AS text, s.ts AS ts, s.kind AS kind, s.author_role AS role, s.url AS url,
       s.author_id AS author, revs
