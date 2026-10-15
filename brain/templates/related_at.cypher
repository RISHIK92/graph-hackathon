// name: related_at
// purpose: entities of one label linked to an entity by one projection type in one direction at V (count_related)
// params: a, p, dir, label, primary, V
// indexes: Entity.id
// golden: tests/test_templates.py::test_goldens[related_at]
// dir 'out': (a)-[p]->(n); 'in': (n)-[p]->(a). Type, direction and label are parameter filters, so one
// static query serves every count (a relationship type can't be a parameter in the pattern).
MATCH (a:Entity {id:$a})-[r]-(n:Entity)
WHERE type(r) = $p AND r.valid_from <= $V AND r.valid_to > $V AND $label IN labels(n)
  AND (($dir = 'out' AND startNode(r).id = $a) OR ($dir = 'in' AND endNode(r).id = $a))
  AND (NOT $primary OR r.primary = true)
RETURN DISTINCT n.id AS id, n.name AS name, r.aid AS aid
ORDER BY name
