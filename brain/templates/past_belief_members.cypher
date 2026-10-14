// name: past_belief_members
// purpose: Cypher past-belief engine, stage 2 (02 §6, A53): per run member at T, the live evidence, the live superseders holding at T (interval end) and the live challengers with their latest authored evidence (settled rule A56).
// params: members (list of assertion ids), T
// indexes: Assertion.id
// golden: tests/test_templates.py::test_goldens[past_belief_members]
UNWIND $members AS mid
MATCH (m:Assertion {id: mid})
// Evidence visible at T (rank >= 1, recorded_at <= T < removed_at); the span ts feeds the settled rule.
WITH m, [(m)-[ev:EVIDENCED_BY]->(s) WHERE ev.authority >= 1 AND ev.recorded_at <= $T AND ev.removed_at > $T
         | {span: s.id, form: ev.form, authority: ev.authority, ts: s.ts}] AS evs
// Every traversal runs BEFORE the one aggregation: on 6.0.1 an OPTIONAL MATCH placed after a collect()
// silently matches nothing (F21/F22 family). The x × c cross product is bounded by the chain cap.
// Superseders: a SUPERSEDES edge live at T into the member, from a record holding at T (conditions 1, 0, 3).
OPTIONAL MATCH (m)<-[sp:SUPERSEDES]-(x)
WHERE sp.recorded_at <= $T AND sp.removed_at > $T AND x.recorded_at <= $T AND x.retracted_at > $T
WITH m, evs, x
// Challengers: a DISPUTES edge live at T into the member, from a record holding by conditions 0 and 1.
OPTIONAL MATCH (m)<-[dp:DISPUTES]-(c)
WHERE dp.recorded_at <= $T AND dp.removed_at > $T AND c.recorded_at <= $T AND c.retracted_at > $T
WITH m, evs, x, c
WITH m, evs, x, c, CASE WHEN x IS NULL THEN [] ELSE [(x)-[ev:EVIDENCED_BY]->() WHERE ev.authority >= 1 AND ev.recorded_at <= $T AND ev.removed_at > $T | ev.authority] END AS xev
WITH m, evs, x, c, xev, CASE WHEN x IS NULL THEN [] ELSE [(x)-[d:DISPUTES]->() WHERE d.recorded_at <= $T AND d.removed_at > $T | d.recorded_at] END AS xd
WITH m, evs, x, c, xev, xd, CASE WHEN c IS NULL THEN [] ELSE [(c)-[ev:EVIDENCED_BY]->(s) WHERE ev.authority >= 1 AND ev.recorded_at <= $T AND ev.removed_at > $T | s.ts] END AS cts
WITH m, evs,
     collect(DISTINCT CASE WHEN x IS NOT NULL AND size(xev) > 0 AND size(xd) = 0 THEN x.valid_from ELSE null END) AS sup_vfs,
     collect(DISTINCT CASE WHEN c IS NOT NULL AND size(cts) > 0
                           THEN {id: c.id, last_ts: reduce(acc = 0, t IN cts | CASE WHEN t > acc THEN t ELSE acc END)}
                           ELSE null END) AS challengers
RETURN m.id AS id, m.valid_from AS valid_from, evs,
       [v IN sup_vfs WHERE v IS NOT NULL] AS sup_vfs,
       [c IN challengers WHERE c IS NOT NULL] AS challengers
