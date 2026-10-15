// name: draft_status
// purpose: the status of the Action that produced a draft Source (withdrawn banner)
// params: id
// indexes: Source.id
// golden: tests/test_templates.py::test_goldens[draft_status]
MATCH (src:Source {id:$id})<-[:PRODUCED]-(ac:Action)
RETURN ac.status AS s
