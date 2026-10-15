// name: entity_sources
// purpose: latest non-draft Sources whose spans mention an entity, grouped by kind (entity panel)
// params: id
// indexes: Entity.id
// golden: tests/test_templates.py::test_goldens[entity_sources]
// Anchored on the entity first: as one pattern the planner starts from the Source.is_latest index.
MATCH (e:Entity {id:$id})
WITH e
MATCH (e)<-[:MENTIONS]-(s:Span)<-[h:HAS_SPAN]-(src:Source)
WHERE src.kind <> 'draft' AND src.is_latest = true
RETURN src.kind AS kind, collect(DISTINCT {id:src.id, title:src.title}) AS sources
