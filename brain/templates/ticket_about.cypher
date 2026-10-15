// name: ticket_about
// purpose: what a ticket is currently about (agent routing to get_owner)
// params: t, m
// indexes: Ticket.id
// golden: tests/test_templates.py::test_goldens[ticket_about]
MATCH (k:Ticket {id:$t})-[a:ABOUT]->(x)
WHERE a.valid_to = $m
RETURN x.id AS x
