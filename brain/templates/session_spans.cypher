// name: session_spans
// purpose: a user's own session turns (recall_session); agent turns are excluded (A61)
// params: user
// indexes: Source.user_id
// golden: tests/test_templates.py::test_goldens[session_spans]
MATCH (src:Source {user_id:$user})-[:HAS_SPAN]->(s:Span)
WHERE src.kind = 'chat_session' AND s.author_role = 'user'
RETURN s.id AS id, s.text AS text, s.ts AS ts
ORDER BY s.ts DESC LIMIT 200
