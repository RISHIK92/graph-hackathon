// name: account_session
// purpose: an account's running chat, its newest chat session in the workspace (chat history, Oct 18)
// params: user
// indexes: Source.user_id
// golden: tests/test_templates.py::test_goldens[account_session]
MATCH (s:Source {user_id:$user})
WHERE s.kind = 'chat_session'
RETURN s.id AS id, s.created_at AS at
ORDER BY s.created_at DESC LIMIT 1
