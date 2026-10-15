// name: session
// purpose: a chat session's user and acting-as person
// params: id
// indexes: Source.id
// golden: tests/test_templates.py::test_goldens[session]
MATCH (s:Source {id:$id})
RETURN s.user_id AS u, s.acting_as AS a
