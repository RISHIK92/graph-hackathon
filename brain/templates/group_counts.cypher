// name: group_counts
// purpose: every entity of one label with its members over one projection type at V, largest first (rank_by_count)
// params: label, p, dir, member_label, primary, V
// indexes: none (ranks every entity of a label; bounded by the world size)
// golden: tests/test_templates.py::test_goldens[group_counts]
// The filter sits inside collect(), not in an OPTIONAL MATCH ... WHERE (6.0.1 Filter placement, see
// decision_trace), so an entity with no members keeps its row with an empty list. The null case comes first:
// type() and startNode() of a missing edge raise a type error.
MATCH (t:Entity) WHERE $label IN labels(t)
OPTIONAL MATCH (t)-[r]-(n:Entity)
WITH t, collect(CASE WHEN r IS NULL THEN null WHEN type(r) = $p AND r.valid_from <= $V AND r.valid_to > $V AND $member_label IN labels(n)
                 AND (($dir = 'out' AND startNode(r).id = t.id) OR ($dir = 'in' AND endNode(r).id = t.id))
                 AND (NOT $primary OR r.primary = true)
            THEN {id:n.id, name:n.name, aid:r.aid} END) AS ms
RETURN t.id AS id, t.name AS name, size(ms) AS n, ms
ORDER BY n DESC, name
