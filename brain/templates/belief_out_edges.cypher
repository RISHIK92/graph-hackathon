// name: belief_out_edges
// purpose: current outgoing projection edges of one type with authority >= 2, for eligibility rules (A57)
// params: x, rel, now
// indexes: Entity.id
// golden: tests/test_templates.py::test_goldens[belief_out_edges]
// The type is a parameter filter: a relationship type can't be a parameter in the pattern.
MATCH (x:Entity {id:$x})-[r]->(y:Entity)
WHERE type(r) = $rel AND r.valid_from <= $now AND r.valid_to > $now AND r.authority >= 2
RETURN y.id AS id, y.name AS name, r.aid AS aid
