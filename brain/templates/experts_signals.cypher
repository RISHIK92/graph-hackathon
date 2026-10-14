// name: experts_signals
// purpose: expertise signals for x at V (03 §1.2 find_experts): authored mentioning spans, ownership/lead/works-on, tickets, deciders
// params: x, V
// indexes: Entity.id
// golden: tests/test_templates.py::test_goldens[experts_signals]
MATCH (x:Entity {id:$x})
OPTIONAL MATCH (x)<-[:MENTIONS]-(s:Span)-[:AUTHORED_BY]->(p:Person)
WHERE s.ts <= $V
WITH x, collect({person:p.id, kind:'authored', ref:s.id, ts:s.ts}) AS authored
OPTIONAL MATCH (x)<-[r:OWNS|WORKS_ON|LEADS]-(p2:Person)
WHERE r.valid_from <= $V AND r.valid_to > $V
WITH x, authored, collect({person:p2.id, kind:type(r), ref:r.aid, ts:r.valid_from}) AS direct
OPTIONAL MATCH (x)<-[o:OWNS]-(t:Team)<-[l:LEADS]-(p3:Person)
WHERE o.valid_from <= $V AND o.valid_to > $V AND l.valid_from <= $V AND l.valid_to > $V
WITH x, authored, direct, collect({person:p3.id, kind:'LEADS', ref:l.aid, ts:l.valid_from}) AS leads
OPTIONAL MATCH (x)<-[ab:ABOUT]-(k:Ticket)-[asg:ASSIGNED_TO]->(p4:Person)
WHERE ab.valid_to > $V AND asg.valid_from <= $V AND asg.valid_to > $V
WITH x, authored, direct, leads, collect({person:p4.id, kind:'ASSIGNED_TO', ref:asg.aid, ts:asg.valid_from}) AS tickets
OPTIONAL MATCH (x)<-[af:AFFECTS]-(d:Decision)-[db:DECIDED_BY]->(p5:Person)
WHERE af.valid_to > $V AND db.valid_to > $V
RETURN authored, direct, leads, tickets, collect({person:p5.id, kind:'DECIDED_BY', ref:db.aid, ts:db.valid_from}) AS decided
