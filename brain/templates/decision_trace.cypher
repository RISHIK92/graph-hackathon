// name: decision_trace
// purpose: a decision's replacement chain (REPLACES*0..5, a named R4 exception), deciders, affects and motivating spans
// params: d, V, T
// indexes: Entity.id
// golden: tests/test_templates.py::test_goldens[decision_trace]
MATCH (d:Decision {id:$d})
OPTIONAL MATCH chain = (d)-[:REPLACES*0..5]->(old:Decision)
WITH d, collect(DISTINCT old.id) AS replaced
// The DECIDED_BY filter sits inside collect(): as an OPTIONAL MATCH ... WHERE after an aggregating WITH,
// 6.0.1 places the Filter below the Conditional Traverse and `deciders` comes back [{null}].
OPTIONAL MATCH (d)-[db:DECIDED_BY]->(who:Entity)
WITH d, replaced, collect(DISTINCT CASE WHEN db.valid_from <= $V AND db.valid_to > $V
                                   THEN {id:who.id, name:who.name, aid:db.aid} END) AS deciders
OPTIONAL MATCH (d)-[af:AFFECTS]->(x:Entity) WHERE af.valid_from <= $V AND af.valid_to > $V
WITH d, replaced, deciders, collect(DISTINCT {id:x.id, name:x.name, aid:af.aid}) AS affects
OPTIONAL MATCH (d)-[m:MOTIVATED_BY]->(s:Span) WHERE m.recorded_at <= $T AND m.removed_at > $T
RETURN d.id AS id, d.name AS name, d.title AS title, d.status AS status, d.status_aid AS status_aid,
       replaced, deciders, affects, collect(DISTINCT {span:s.id, section:m.section, action_id:m.action_id}) AS motivated
