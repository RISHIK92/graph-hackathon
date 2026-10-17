// name: chat_turns
// purpose: a chat session's user turns in order, with the events and trace kept when each finished
// params: s
// indexes: Source.id
// golden: tests/test_templates.py::test_goldens[chat_turns]
MATCH (src:Source {id:$s})-[h:HAS_SPAN]->(x:Span)
WHERE x.author_role = 'user'
RETURN x.text AS text, x.ts AS ts, x.author_id AS actor, x.chat AS chat
ORDER BY h.ordinal
