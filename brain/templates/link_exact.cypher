// name: link_exact
// purpose: exact id or alias match for entity linking (03 §1.2 link_entities step 1)
// params: q (normalised lower-case mention)
// indexes: Entity.aliases (array range), Entity.id
// golden: tests/test_templates.py::test_goldens[link_exact]
MATCH (e:Entity) WHERE $q IN e.aliases
RETURN e.id AS id, e.name AS name, labels(e) AS labels
UNION
MATCH (e:Entity {id:$q})
RETURN e.id AS id, e.name AS name, labels(e) AS labels
