// name: paths_between
// purpose: up to 20 paths of at most h (1 to 3) hops of the given projection types between two entities, valid at V (find_paths)
// params: a, b, V, h, types
// indexes: Entity.id
// golden: tests/test_templates.py::test_goldens[paths_between]
// The type list is registry.PROJECTION_TYPES (a test keeps them equal); the hop bound and the type subset
// are parameter filters because neither can be a parameter in the pattern.
MATCH p = (a:Entity {id:$a})-[:ABOUT|AFFECTS|ASSIGNED_TO|DECIDED_BY|DEPENDS_ON|LEADS|MEMBER_OF|OWNS|PART_OF|REPLACES|WORKS_ON*1..3]-(b:Entity {id:$b})
WHERE length(p) <= $h AND all(e IN relationships(p) WHERE type(e) IN $types AND e.valid_from <= $V AND e.valid_to > $V)
RETURN [n IN nodes(p) | {id:n.id, name:n.name}] AS ns,
       [e IN relationships(p) | {type:type(e), aid:e.aid, vf:e.valid_from, vt:e.valid_to, from:startNode(e).id}] AS es
LIMIT 20
