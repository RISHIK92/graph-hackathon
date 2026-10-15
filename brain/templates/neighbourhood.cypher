// name: neighbourhood
// purpose: projection edges within h (1 or 2) hops of the given entities, valid at V (GET /graph/neighbourhood)
// params: ids, V, h
// indexes: Entity.id
// golden: tests/test_templates.py::test_goldens[neighbourhood]
// The type list is registry.PROJECTION_TYPES (a test keeps them equal); the hop bound is a parameter
// filter because a variable-length bound can't be a parameter.
UNWIND $ids AS i
MATCH p = (x:Entity {id:i})-[:ABOUT|AFFECTS|ASSIGNED_TO|DECIDED_BY|DEPENDS_ON|LEADS|MEMBER_OF|OWNS|PART_OF|REPLACES|WORKS_ON*1..2]-(y:Entity)
WHERE length(p) <= $h AND all(e IN relationships(p) WHERE e.aid IS NOT NULL AND e.valid_from <= $V AND e.valid_to > $V)
UNWIND relationships(p) AS e
RETURN DISTINCT startNode(e).id AS source, endNode(e).id AS target, type(e) AS type, e.aid AS aid LIMIT 300
