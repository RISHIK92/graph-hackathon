// name: past_belief_run
// purpose: Cypher past-belief engine, stage 1 (02 §6, A53): survivors at (T, V) and the run rebuilt at T from CONTINUES edges live at T. Never reads run_id or status.
// params: chain, T, V
// indexes: Assertion.chain_id
// golden: tests/test_templates.py::test_goldens[past_belief_run]
// Condition 1 (recorded_at <= T < retracted_at) and condition 2 (valid_from <= V) on the candidate.
MATCH (a:Assertion {chain_id:$chain})
WHERE a.recorded_at <= $T AND a.retracted_at > $T AND a.valid_from <= $V
// Condition 0 (live rank >= 1 evidence) and condition 3 (no DISPUTES edge live at T), one filtered
// comprehension per WITH (R12). Both are projected BEFORE the single filter: on 6.0.1 a traversal that
// follows a `WITH a WHERE size(<comprehension>)` stage silently returns nothing (F21/F22 family).
WITH a, [(a)-[ev:EVIDENCED_BY]->() WHERE ev.authority >= 1 AND ev.recorded_at <= $T AND ev.removed_at > $T | ev.authority] AS ev0
WITH a, ev0, [(a)-[d:DISPUTES]->() WHERE d.recorded_at <= $T AND d.removed_at > $T | d.recorded_at] AS d0
WITH a WHERE size(ev0) > 0 AND size(d0) = 0
// Condition 4: a blocker is a later record on a path of SUPERSEDES|CONTINUES edges all live at T (R1: b unlabelled)
// that holds at T by conditions 0, 1 and 3, with valid_from <= V. Bounded by the chain cap (I11, R4 exception).
OPTIONAL MATCH p = (a)<-[:SUPERSEDES|CONTINUES*1..50]-(b)
WHERE b.recorded_at <= $T AND b.retracted_at > $T AND b.valid_from <= $V
  AND all(e IN relationships(p) WHERE e.recorded_at <= $T AND e.removed_at > $T)
WITH DISTINCT a, b
WITH a, b, CASE WHEN b IS NULL THEN [] ELSE [(b)-[ev:EVIDENCED_BY]->() WHERE ev.authority >= 1 AND ev.recorded_at <= $T AND ev.removed_at > $T | ev.authority] END AS bev
WITH a, b, bev, CASE WHEN b IS NULL THEN [] ELSE [(b)-[d:DISPUTES]->() WHERE d.recorded_at <= $T AND d.removed_at > $T | d.recorded_at] END AS bd
WITH a, collect(CASE WHEN b IS NOT NULL AND size(bev) > 0 AND size(bd) = 0 THEN b.id ELSE null END) AS blockers
WITH a, [x IN blockers WHERE x IS NOT NULL] AS blockers
WITH a WHERE size(blockers) = 0
// The run at T: CONTINUES edges live at T in both directions, over records holding at T by condition 1.
OPTIONAL MATCH q = (a)-[:CONTINUES*1..50]-(m)
WHERE m.recorded_at <= $T AND m.retracted_at > $T
  AND all(e IN relationships(q) WHERE e.recorded_at <= $T AND e.removed_at > $T)
WITH a, collect(DISTINCT m.id) AS others
RETURN a.id AS id, a.subject_id AS subject_id, a.object_id AS object_id, a.object_value AS object_value,
       a.negated AS negated, a.valid_from AS valid_from, others
ORDER BY a.valid_from, a.id
