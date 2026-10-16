# Graph performance (862fdcf)

Client-side ms per query as `brain.db.Graph` logs it (QueryLog), so every number includes the network round trip to FalkorDB in local Docker; tool and rebuild times are wall-clock around the call. Offline (`BRAIN_LLM=off`). World and workload: see the `evals/perf.py` docstring. p95 is nearest-rank, so with a small n it is close to the max and sensitive to other load on the host. PROFILE runs once per template after the workload, on its slowest call's parameters (the graph then also holds the workload's sessions and actions).

## Targets at 10x

| Version | Target | Result | Met |
|---|---|---|---|
| 6.0.1 | every read template p95 <= 50 ms | worst directory_tickets 325.8 ms; over: all_entities, directory_people, directory_tickets, graph_edge_kinds, graph_edges, graph_nodes, integrity_chains, integrity_i1, names, snap_betweenness, snapshot_touches, unsupported | missed |
| 6.0.1 | snapshot rebuild <= 2 s | max 0.788 s (p50 0.517 s) | met |
| 6.0.1 | algorithm tools p95 <= 200 ms | worst knowledge_gaps 213.8 ms | missed |
| 4.22.0 | every read template p95 <= 50 ms | worst graph_edges 308.1 ms; over: directory_tickets, experts_signals, graph_edge_kinds, graph_edges, graph_nodes, integrity_i1, integrity_i5, snap_betweenness, snapshot_touches, stale_detection, unsupported | missed |
| 4.22.0 | snapshot rebuild <= 2 s | max 0.619 s (p50 0.275 s) | met |
| 4.22.0 | algorithm tools p95 <= 200 ms | worst key_people 155.6 ms | met |

## Reading the results

Run on Oct 16 at 14:45 IST on HEAD 862fdcf, after the main session's live eval had finished. The two FalkorDB
containers are shared, and the main session's test suite ran on them now and then during this run. The single
spikes (p95 or max far above p50 for the same template) come from that and from client-side GC.

**Fixed (before -> after, p50 at 10x, measured on the same 10x graph with 20 repetitions):**

| Template | 6.0.1 | 4.22.0 | Cause and fix |
|---|---|---|---|
| stale_override | 750 -> 2.6 ms | 30 -> 11 ms | 6.0.1 skipped the `Assertion.run_id` index for `MATCH (m:Assertion {run_id: old.run_id})` after a WITH and walked every EVIDENCED_BY edge per row (F27). The template now starts at the live SUPERSEDES edges and projects `old.run_id` through WITH before the index lookup (commit 40bdd2b) |
| graph_ticks | 98 -> 6 ms | 246 -> 14 ms | `MATCH ()-[e]->()` walked all 87k edges. Projection edges join two entities, so `(:Entity)-[e]->(:Entity)` gives the same rows (commit 862fdcf) |

In the before run, stale_override had p95 985 ms on 6.0.1 and graph_ticks 441 ms on 4.22.0. Neither is over
target now.

**Still missed at 10x, and why:**
- **Whole-graph and whole-list reads** (graph_nodes, graph_edges, graph_edge_kinds, directory_tickets,
  directory_people, all_entities, names, snapshot_touches): server time is 2-15 ms in every PROFILE. The rest is
  moving and parsing 400-4,700 rows in the Python client (plus, for graph_edge_kinds, a 2,746-id parameter list).
  p50 is 17-55 ms, except graph_edge_kinds (98 ms on 6.0.1, 41 ms on 4.22.0) and snapshot_touches (84 / 62 ms).
  The p95 values over 100 ms are single spikes. These are bounded by world size, not by a bad plan. A real fix
  is a smaller payload (paging, or merging graph_edge_kinds into graph_edges), which is an API change and out of
  scope here.
- **snap_betweenness**: the `algo.betweenness` procedure itself (about 95-110 ms server time at 10x). The design
  asks for exact betweenness (`samplingSize` >= node count), so the cost grows as V·E. key_people stays within
  its 200 ms target on both versions.
- **knowledge_gaps on 6.0.1**: p50 127 ms, p95 214 ms (target 200 ms). That p95 is the second highest of 20
  runs while the host was shared. On 4.22.0: p95 88 ms.
- **One-off sweeps** (n = 1: integrity_i1, integrity_i5, integrity_chains, unsupported): admin integrity checks
  and the end-of-ingest retraction sweep scan every assertion. They are not on the answer path. unsupported is
  23 ms p50 on 6.0.1 and 52 ms on 4.22.0 (4.22.0 is slow walking the 6k EVIDENCED_BY edges).
- **experts_signals and stale_detection on 4.22.0**: about 3 ms server time; the client p50 is 34-78 ms on the
  fallback version only. On 6.0.1 they are 2-11 ms.

## FalkorDB 6.0.1, scale 1x

Graph: 2618 nodes, 6913 edges (143 entities, 569 assertions, 1008 spans); built in 17.3 s. Workload: 445 questions.

| Algorithm tool | n | p50 ms | p95 ms | max ms |
|---|---|---|---|---|
| critical_systems | 20 | 14.5 | 15.8 | 17.4 |
| connection_between | 20 | 15.1 | 21.6 | 22.0 |
| key_people | 20 | 13.1 | 18.1 | 18.4 |
| knowledge_gaps | 20 | 10.6 | 29.7 | 65.1 |

Snapshot rebuild, cold, 5 runs: 0.156, 0.048, 0.043, 0.044, 0.04 s.

Guarded write (`write_plan`, not a target): n 1353, p50 7.2 ms, p95 16.8 ms.

| Template | n | p50 ms | p95 ms | max ms |
|---|---|---|---|---|
| graph_edge_kinds | 22 | 2.9 | 17.2 | 18.6 |
| integrity_i1 | 1 | 11.5 | 11.5 | 11.5 |
| snapshot_touches | 7 | 5.9 | 9.9 | 9.9 |
| graph_edges | 29 | 3.8 | 9.3 | 80.4 |
| unsupported | 1 | 7.2 | 7.2 | 7.2 |
| all_entities | 3 | 5.2 | 6.9 | 6.9 |
| directory_tickets | 22 | 2.1 | 5.8 | 6.9 |
| integrity_chains | 1 | 5.7 | 5.7 | 5.7 |
| entity_names | 1411 | 1.3 | 5.1 | 146.1 |
| snap_wcc | 21 | 0.9 | 4.6 | 152.3 |
| directory_people | 72 | 1.8 | 4.1 | 8.0 |
| graph_nodes | 29 | 1.6 | 3.9 | 4.3 |
| stale_detection | 22 | 1.4 | 3.1 | 3.3 |
| overview_teams | 94 | 1.0 | 2.9 | 8.6 |
| people | 20 | 1.0 | 2.5 | 2.7 |
| search_fulltext | 18 | 0.5 | 2.4 | 2.4 |
| related_at | 60 | 0.4 | 2.3 | 8.2 |
| directory_decisions | 22 | 1.0 | 2.2 | 2.3 |
| search_vector | 18 | 0.9 | 2.2 | 2.2 |
| directory_systems | 22 | 0.8 | 2.1 | 2.8 |
| experts_signals | 5 | 1.5 | 2.1 | 2.1 |
| link_vector | 486 | 0.7 | 2.1 | 158.9 |
| snap_betweenness | 21 | 1.1 | 2.1 | 13.4 |
| directory_projects | 22 | 0.6 | 1.9 | 3.9 |
| graph_ticks | 22 | 1.1 | 1.7 | 2.4 |
| names | 1 | 1.6 | 1.6 | 1.6 |
| owner_at | 247 | 0.3 | 1.6 | 10.1 |
| group_counts | 2 | 1.0 | 1.5 | 1.5 |
| decision_trace | 291 | 0.4 | 1.4 | 11.2 |
| span_details | 1410 | 0.4 | 1.4 | 21.2 |
| depends_on | 15 | 0.2 | 1.3 | 1.3 |
| recent_actions | 50 | 0.5 | 1.3 | 2.2 |
| stale_override | 22 | 0.6 | 1.2 | 1.3 |
| assertions_by_id | 1580 | 0.3 | 1.1 | 6.4 |
| impact_dependents | 29 | 0.3 | 1.1 | 2.9 |
| belief_out_edges | 2232 | 0.3 | 1.0 | 34.5 |
| demo_identity | 1 | 1.0 | 1.0 | 1.0 |
| evidence_fragment | 1258 | 0.3 | 1.0 | 8.0 |
| link_exact | 486 | 0.3 | 1.0 | 19.0 |
| overview_decisions | 94 | 0.3 | 1.0 | 5.9 |
| snap_paths | 26 | 0.4 | 1.0 | 1.1 |
| ticket_about | 70 | 0.3 | 1.0 | 2.0 |
| lead_at | 253 | 0.3 | 0.9 | 3.0 |
| link_fulltext | 486 | 0.3 | 0.9 | 15.5 |
| entity_sources | 71 | 0.3 | 0.8 | 1.1 |
| overview_pending | 94 | 0.3 | 0.8 | 3.2 |
| proposals_about | 291 | 0.2 | 0.8 | 6.2 |
| snap_pagerank | 22 | 0.3 | 0.8 | 121.8 |
| stated_by_latest | 1 | 0.8 | 0.8 | 0.8 |
| action | 1656 | 0.3 | 0.7 | 27.6 |
| action_read | 1739 | 0.3 | 0.7 | 3.9 |
| chains_for_entity | 289 | 0.2 | 0.7 | 24.3 |
| decisions_affecting | 28 | 0.3 | 0.7 | 1.1 |
| neighbourhood | 61 | 0.3 | 0.7 | 1.9 |
| session_spans | 50 | 0.3 | 0.7 | 1.9 |
| turn_count | 348 | 0.2 | 0.7 | 17.7 |
| assertion | 843 | 0.2 | 0.6 | 3.1 |
| based_on_spans | 144 | 0.2 | 0.6 | 1.9 |
| belief_lead_of | 1689 | 0.2 | 0.6 | 37.9 |
| belief_owners_of | 1389 | 0.3 | 0.6 | 157.2 |
| decision_status | 144 | 0.2 | 0.6 | 4.6 |
| dispute_chains | 148 | 0.2 | 0.6 | 1.9 |
| integrity_i11 | 1 | 0.6 | 0.6 | 0.6 |
| produced_assertions | 1488 | 0.2 | 0.6 | 54.3 |
| proposal_links | 2815 | 0.2 | 0.6 | 5.4 |
| replaced_by | 291 | 0.2 | 0.6 | 4.5 |
| replaces_out | 291 | 0.2 | 0.6 | 4.0 |
| snap_leaders | 42 | 0.2 | 0.6 | 6.7 |
| already_confirmed | 600 | 0.2 | 0.5 | 11.8 |
| doc_evidence | 1 | 0.5 | 0.5 | 0.5 |
| entity | 71 | 0.2 | 0.5 | 0.6 |
| entity_name | 1453 | 0.2 | 0.5 | 11.7 |
| integrity_i5 | 1 | 0.5 | 0.5 | 0.5 |
| produced_sources | 1488 | 0.2 | 0.5 | 78.3 |
| rationale_spans | 144 | 0.2 | 0.5 | 1.9 |
| run_members | 2042 | 0.2 | 0.5 | 5.5 |
| snap_owns | 21 | 0.3 | 0.5 | 0.6 |
| source_exists | 2 | 0.2 | 0.5 | 0.5 |
| strongest_member | 3538 | 0.2 | 0.5 | 31.3 |
| belief_all_leads | 63 | 0.2 | 0.4 | 1.4 |
| current_in_chain | 50 | 0.2 | 0.4 | 0.5 |
| disputed_run | 189 | 0.2 | 0.4 | 2.7 |
| existing_spans | 1 | 0.4 | 0.4 | 0.4 |
| live_confirmations | 189 | 0.2 | 0.4 | 5.8 |
| nodes_by_id | 61 | 0.2 | 0.4 | 1.4 |
| person_name | 1739 | 0.2 | 0.4 | 2.5 |
| snap_part_of | 21 | 0.3 | 0.4 | 0.4 |
| snap_person_edges | 105 | 0.2 | 0.4 | 1.3 |
| snapshot_version | 91 | 0.2 | 0.4 | 0.9 |
| span_facts | 17 | 0.2 | 0.4 | 0.4 |
| confirms_of | 4 | 0.2 | 0.3 | 0.3 |
| latest_spans | 1 | 0.3 | 0.3 | 0.3 |
| learn_ents | 4 | 0.2 | 0.3 | 0.3 |
| proposal_ends | 1068 | 0.2 | 0.3 | 1.7 |
| revisions | 2 | 0.2 | 0.3 | 0.3 |
| snap_dependents | 110 | 0.1 | 0.3 | 1.3 |
| source_view | 20 | 0.2 | 0.3 | 1.3 |
| span_view | 20 | 0.2 | 0.3 | 0.5 |
| turn_span | 4 | 0.2 | 0.3 | 0.3 |
| withdrawn_by | 24 | 0.2 | 0.3 | 0.8 |
| action_log | 10 | 0.2 | 0.2 | 0.2 |
| dispute_edge | 264 | 0.2 | 0.2 | 0.5 |
| integrity_sentinel | 1 | 0.2 | 0.2 | 0.2 |
| pending_proposals | 10 | 0.2 | 0.2 | 0.2 |
| snap_meta | 88 | 0.1 | 0.2 | 0.3 |
| snap_node_count | 21 | 0.1 | 0.2 | 0.2 |
| statement | 125 | 0.1 | 0.2 | 0.5 |

## FalkorDB 6.0.1, scale 10x

Graph: 26279 nodes, 69346 edges (1430 entities, 5726 assertions, 10116 spans); built in 155.2 s. Workload: 476 questions.

| Algorithm tool | n | p50 ms | p95 ms | max ms |
|---|---|---|---|---|
| critical_systems | 20 | 43.0 | 71.5 | 71.8 |
| connection_between | 20 | 3.9 | 8.1 | 10.4 |
| key_people | 20 | 87.7 | 118.4 | 123.5 |
| knowledge_gaps | 20 | 127.2 | 213.8 | 222.0 |

Snapshot rebuild, cold, 5 runs: 0.788, 0.517, 0.644, 0.284, 0.359 s.

Guarded write (`write_plan`, not a target): n 1353, p50 20.4 ms, p95 66.6 ms.

| Template | n | p50 ms | p95 ms | max ms |
|---|---|---|---|---|
| directory_tickets | 22 | 48.1 | 325.8 | 1839.5 |
| graph_edge_kinds | 22 | 98.3 | 259.4 | 279.8 |
| graph_nodes | 29 | 19.7 | 248.0 | 313.5 |
| graph_edges | 29 | 54.9 | 210.1 | 273.3 |
| snapshot_touches | 7 | 83.6 | 109.0 | 109.0 |
| integrity_i1 | 1 | 103.8 | 103.8 | 103.8 |
| snap_betweenness | 21 | 49.6 | 82.1 | 96.5 |
| directory_people | 112 | 34.0 | 78.5 | 311.3 |
| integrity_chains | 1 | 68.8 | 68.8 | 68.8 |
| names | 1 | 57.7 | 57.7 | 57.7 |
| unsupported | 1 | 56.0 | 56.0 | 56.0 |
| all_entities | 3 | 25.5 | 50.7 | 50.7 |
| stale_detection | 22 | 21.9 | 47.7 | 79.3 |
| directory_decisions | 22 | 10.5 | 41.5 | 190.7 |
| overview_teams | 134 | 10.7 | 38.3 | 319.7 |
| directory_systems | 22 | 11.7 | 33.5 | 54.5 |
| group_counts | 2 | 12.9 | 33.3 | 33.3 |
| people | 20 | 21.0 | 27.3 | 30.7 |
| snap_wcc | 21 | 8.4 | 22.9 | 65.2 |
| entity_names | 1772 | 7.3 | 19.5 | 912.1 |
| related_at | 66 | 1.1 | 18.5 | 101.9 |
| directory_projects | 22 | 6.3 | 18.3 | 39.0 |
| search_fulltext | 20 | 1.7 | 17.8 | 41.1 |
| search_vector | 20 | 10.0 | 16.4 | 28.9 |
| dispute_chains | 188 | 1.3 | 16.0 | 59.0 |
| stale_override | 22 | 7.0 | 13.9 | 17.9 |
| demo_identity | 1 | 12.5 | 12.5 | 12.5 |
| graph_ticks | 22 | 7.7 | 12.3 | 18.3 |
| experts_signals | 5 | 5.7 | 10.1 | 10.1 |
| snap_leaders | 42 | 0.7 | 9.2 | 14.8 |
| span_view | 20 | 0.8 | 7.8 | 8.1 |
| overview_pending | 134 | 1.6 | 7.1 | 37.4 |
| link_vector | 521 | 1.2 | 6.2 | 246.9 |
| overview_decisions | 134 | 2.0 | 5.6 | 29.1 |
| integrity_i11 | 1 | 5.4 | 5.4 | 5.4 |
| snapshot_version | 92 | 1.0 | 5.3 | 29.0 |
| snap_pagerank | 23 | 1.2 | 5.2 | 53.7 |
| belief_all_leads | 424 | 1.0 | 3.9 | 16.4 |
| source_view | 20 | 1.1 | 3.9 | 4.3 |
| turn_span | 4 | 0.4 | 3.7 | 3.7 |
| integrity_i5 | 1 | 3.6 | 3.6 | 3.6 |
| snap_owns | 21 | 1.9 | 3.6 | 13.9 |
| ticket_about | 72 | 0.6 | 3.6 | 34.5 |
| pending_proposals | 10 | 0.5 | 3.4 | 3.4 |
| span_details | 1656 | 0.6 | 3.4 | 49.5 |
| chains_for_entity | 432 | 0.3 | 2.9 | 33.0 |
| link_fulltext | 521 | 0.6 | 2.9 | 27.6 |
| span_facts | 17 | 0.3 | 2.9 | 2.9 |
| snap_paths | 26 | 0.3 | 2.6 | 3.3 |
| snap_part_of | 21 | 1.2 | 2.5 | 3.8 |
| assertions_by_id | 1833 | 0.4 | 2.2 | 10.3 |
| decision_trace | 310 | 0.6 | 2.2 | 29.4 |
| nodes_by_id | 122 | 0.3 | 2.2 | 3.6 |
| belief_out_edges | 2232 | 0.6 | 2.1 | 59.3 |
| link_exact | 521 | 0.4 | 2.1 | 18.2 |
| belief_owners_of | 2474 | 0.4 | 2.0 | 20.1 |
| decision_status | 144 | 0.5 | 2.0 | 23.8 |
| neighbourhood | 122 | 0.5 | 2.0 | 3.0 |
| entity_sources | 132 | 0.4 | 1.9 | 6.0 |
| based_on_spans | 144 | 0.3 | 1.8 | 6.3 |
| decisions_affecting | 44 | 0.3 | 1.8 | 2.7 |
| disputed_run | 1274 | 0.3 | 1.8 | 27.0 |
| owner_at | 331 | 0.4 | 1.8 | 5.9 |
| evidence_fragment | 1483 | 0.4 | 1.7 | 8.4 |
| live_confirmations | 1274 | 0.3 | 1.7 | 13.5 |
| statement | 1241 | 0.2 | 1.7 | 322.5 |
| assertion | 1928 | 0.3 | 1.6 | 47.5 |
| confirms_of | 4 | 0.5 | 1.6 | 1.6 |
| snap_person_edges | 105 | 0.4 | 1.6 | 4.1 |
| belief_lead_of | 2774 | 0.3 | 1.5 | 52.3 |
| snap_dependents | 115 | 0.3 | 1.5 | 3.9 |
| action | 1656 | 0.4 | 1.4 | 6.9 |
| entity_name | 1357 | 0.2 | 1.4 | 30.2 |
| integrity_sentinel | 1 | 1.4 | 1.4 | 1.4 |
| entity | 132 | 0.2 | 1.3 | 6.7 |
| produced_assertions | 1488 | 0.3 | 1.3 | 10.8 |
| recent_actions | 50 | 0.7 | 1.3 | 3.6 |
| session_spans | 50 | 0.6 | 1.3 | 1.7 |
| action_read | 1739 | 0.4 | 1.2 | 9.7 |
| already_confirmed | 600 | 0.3 | 1.2 | 4.7 |
| existing_spans | 1 | 1.2 | 1.2 | 1.2 |
| impact_dependents | 45 | 0.3 | 1.2 | 3.1 |
| replaced_by | 310 | 0.3 | 1.2 | 5.9 |
| run_members | 4167 | 0.2 | 1.2 | 26.1 |
| proposal_links | 2817 | 0.3 | 1.1 | 6.3 |
| proposals_about | 310 | 0.3 | 1.1 | 5.7 |
| rationale_spans | 144 | 0.3 | 1.1 | 8.8 |
| snap_meta | 89 | 0.2 | 1.1 | 7.7 |
| source_exists | 2 | 0.3 | 1.1 | 1.1 |
| lead_at | 343 | 0.3 | 1.0 | 4.8 |
| replaces_out | 310 | 0.3 | 1.0 | 9.1 |
| strongest_member | 3538 | 0.2 | 1.0 | 32.6 |
| turn_count | 348 | 0.4 | 1.0 | 5.3 |
| action_log | 10 | 0.3 | 0.9 | 0.9 |
| produced_sources | 1488 | 0.3 | 0.9 | 7.3 |
| withdrawn_by | 24 | 0.3 | 0.9 | 3.5 |
| current_in_chain | 50 | 0.3 | 0.8 | 1.2 |
| person_name | 1739 | 0.2 | 0.8 | 4.9 |
| proposal_ends | 1068 | 0.2 | 0.8 | 8.8 |
| depends_on | 30 | 0.3 | 0.7 | 0.8 |
| dispute_edge | 2640 | 0.2 | 0.5 | 5.5 |
| doc_evidence | 1 | 0.5 | 0.5 | 0.5 |
| learn_ents | 4 | 0.3 | 0.5 | 0.5 |
| revisions | 2 | 0.4 | 0.5 | 0.5 |
| snap_node_count | 21 | 0.2 | 0.5 | 0.7 |
| stated_by_latest | 1 | 0.5 | 0.5 | 0.5 |
| latest_spans | 1 | 0.3 | 0.3 | 0.3 |

### PROFILE directory_tickets (6.0.1, 10x)

```
Sort | Records produced: 600, Execution time: 1.033899 ms
    Aggregate | Records produced: 600, Execution time: 7.011172 ms
        Optional | Records produced: 600, Execution time: 0.107790 ms
            Aggregate | Records produced: 600, Execution time: 12.335830 ms
                Apply | Records produced: 600, Execution time: 0.281703 ms
                    Aggregate | Records produced: 600, Execution time: 5.252868 ms
                        Apply | Records produced: 600, Execution time: 0.029792 ms
                            Node By Label Scan | (k:Ticket) | Records produced: 600, Execution time: 0.022958 ms
                            Optional | Records produced: 0, Execution time: 0.000000 ms
                                Filter | Records produced: 600, Execution time: 0.146415 ms
                                    Filter | Records produced: 600, Execution time: 0.032498 ms
                                        Edge By Index Scan | (k)-[ab:ABOUT]->(x:Entity) | Records produced: 600, Execution time: 15.061201 ms
                                            Argument | Records produced: 0, Execution time: 0.000000 ms
                    Optional | Records produced: 0, Execution time: 0.000000 ms
                        Filter | Records produced: 420, Execution time: 0.143039 ms
                            Filter | Records produced: 420, Execution time: 0.057957 ms
                                Edge By Index Scan | (p)-[a:ASSIGNED_TO]->(k:Ticket) | Records produced: 420, Execution time: 15.486819 ms
                                    Argument | Records produced: 0, Execution time: 0.000000 ms
            Filter | Records produced: 600, Execution time: 6.776719 ms
                Node By Index Scan | (st:Assertion) | Records produced: 600, Execution time: 26.052387 ms
                    Argument | Records produced: 0, Execution time: 0.000000 ms
```

### PROFILE graph_edge_kinds (6.0.1, 10x)

```
Aggregate | Records produced: 2746, Execution time: 28.701300 ms
    Filter | Records produced: 3536, Execution time: 1.479185 ms
        Conditional Traverse | (a)-[ev:EVIDENCED_BY]->(s:Span) | Records produced: 3886, Execution time: 1.219102 ms
            Filter | Records produced: 3526, Execution time: 22.687113 ms
                Node By Index Scan | (a:Assertion) | Records produced: 3526, Execution time: 46.607286 ms
```

### PROFILE graph_nodes (6.0.1, 10x)

```
Project | Records produced: 1574, Execution time: 2.997823 ms
    Node By Label Scan | (n:Entity) | Records produced: 1574, Execution time: 0.054582 ms
```

### PROFILE graph_edges (6.0.1, 10x)

```
Project | Records produced: 2746, Execution time: 3.843434 ms
    Filter | Records produced: 2746, Execution time: 18.315228 ms
        Conditional Traverse | (a)-[e]->(b:Entity) | Records produced: 3041, Execution time: 5.991066 ms
            Node By Label Scan | (a:Entity) | Records produced: 1574, Execution time: 0.023582 ms
```

### PROFILE snapshot_touches (6.0.1, 10x)

```
Aggregate | Records produced: 4690, Execution time: 36.932746 ms
    Filter | Records produced: 6920, Execution time: 0.892735 ms
        Conditional Traverse | (s)->(x:Entity) | Records produced: 7090, Execution time: 31.748290 ms
            Filter | Records produced: 5550, Execution time: 0.370660 ms
                Conditional Traverse | (p)<-(s:Span) | Records produced: 5550, Execution time: 4.027473 ms
                    Node By Label Scan | (p:Person) | Records produced: 400, Execution time: 0.016791 ms
```

## FalkorDB 4.22.0, scale 1x

Graph: 2618 nodes, 6913 edges (143 entities, 569 assertions, 1008 spans); built in 10.4 s. Workload: 445 questions.

| Algorithm tool | n | p50 ms | p95 ms | max ms |
|---|---|---|---|---|
| critical_systems | 20 | 17.2 | 20.8 | 21.8 |
| connection_between | 20 | 17.9 | 22.3 | 22.4 |
| key_people | 20 | 15.8 | 80.9 | 82.8 |
| knowledge_gaps | 20 | 10.1 | 11.8 | 12.0 |

Snapshot rebuild, cold, 5 runs: 0.042, 0.043, 0.031, 0.033, 0.027 s.

Guarded write (`write_plan`, not a target): n 1353, p50 4.2 ms, p95 8.7 ms.

| Template | n | p50 ms | p95 ms | max ms |
|---|---|---|---|---|
| all_entities | 3 | 8.0 | 34.5 | 34.5 |
| graph_edges | 29 | 7.0 | 18.9 | 22.5 |
| snap_betweenness | 21 | 1.8 | 14.0 | 26.3 |
| graph_edge_kinds | 22 | 4.3 | 11.4 | 11.8 |
| unsupported | 1 | 11.4 | 11.4 | 11.4 |
| experts_signals | 5 | 4.1 | 8.4 | 8.4 |
| people | 20 | 1.6 | 7.5 | 14.1 |
| stale_detection | 22 | 3.7 | 7.5 | 8.6 |
| directory_tickets | 22 | 4.1 | 6.3 | 7.1 |
| snapshot_touches | 7 | 5.8 | 6.3 | 6.3 |
| directory_decisions | 22 | 1.5 | 5.6 | 6.3 |
| entity_names | 1411 | 2.3 | 5.6 | 225.9 |
| directory_people | 72 | 2.0 | 5.1 | 6.3 |
| names | 1 | 5.1 | 5.1 | 5.1 |
| integrity_i5 | 1 | 4.9 | 4.9 | 4.9 |
| graph_nodes | 29 | 1.9 | 4.7 | 5.8 |
| graph_ticks | 22 | 2.3 | 4.5 | 12.7 |
| search_vector | 18 | 1.1 | 3.9 | 3.9 |
| integrity_i1 | 1 | 3.5 | 3.5 | 3.5 |
| overview_teams | 94 | 1.1 | 3.4 | 19.2 |
| directory_systems | 22 | 1.2 | 3.3 | 4.4 |
| stale_override | 22 | 1.6 | 3.2 | 7.0 |
| integrity_i11 | 1 | 3.1 | 3.1 | 3.1 |
| integrity_chains | 1 | 2.9 | 2.9 | 2.9 |
| directory_projects | 22 | 0.9 | 2.5 | 2.9 |
| group_counts | 2 | 1.9 | 2.5 | 2.5 |
| link_vector | 486 | 0.7 | 2.1 | 8.1 |
| decisions_affecting | 28 | 0.2 | 2.0 | 3.9 |
| overview_decisions | 94 | 0.4 | 1.9 | 6.0 |
| recent_actions | 50 | 0.8 | 1.9 | 2.4 |
| snap_pagerank | 22 | 0.4 | 1.8 | 76.0 |
| belief_out_edges | 2232 | 0.6 | 1.7 | 17.3 |
| snap_wcc | 21 | 1.0 | 1.6 | 19.0 |
| decision_trace | 291 | 0.6 | 1.5 | 30.9 |
| span_details | 1428 | 0.5 | 1.5 | 11.0 |
| current_in_chain | 50 | 0.4 | 1.4 | 4.1 |
| dispute_chains | 148 | 0.4 | 1.3 | 3.8 |
| session_spans | 50 | 0.7 | 1.3 | 3.5 |
| action_read | 1739 | 0.5 | 1.2 | 5.3 |
| assertions_by_id | 1602 | 0.3 | 1.2 | 7.8 |
| evidence_fragment | 1280 | 0.3 | 1.2 | 6.6 |
| turn_span | 4 | 0.5 | 1.2 | 1.2 |
| chains_for_entity | 289 | 0.2 | 1.1 | 6.0 |
| ticket_about | 70 | 0.5 | 1.1 | 3.2 |
| owner_at | 247 | 0.2 | 1.0 | 3.4 |
| produced_assertions | 1488 | 0.4 | 1.0 | 9.9 |
| source_exists | 2 | 0.4 | 1.0 | 1.0 |
| turn_count | 348 | 0.5 | 1.0 | 2.8 |
| action | 1656 | 0.4 | 0.9 | 19.2 |
| assertion | 843 | 0.3 | 0.9 | 9.9 |
| confirms_of | 4 | 0.7 | 0.9 | 0.9 |
| doc_evidence | 1 | 0.9 | 0.9 | 0.9 |
| entity_sources | 71 | 0.3 | 0.9 | 1.7 |
| impact_dependents | 29 | 0.3 | 0.9 | 2.2 |
| link_exact | 486 | 0.3 | 0.9 | 15.8 |
| link_fulltext | 486 | 0.3 | 0.9 | 5.2 |
| search_fulltext | 18 | 0.6 | 0.9 | 0.9 |
| stated_by_latest | 1 | 0.9 | 0.9 | 0.9 |
| belief_owners_of | 1389 | 0.3 | 0.8 | 120.9 |
| demo_identity | 1 | 0.8 | 0.8 | 0.8 |
| disputed_run | 189 | 0.2 | 0.8 | 2.1 |
| existing_spans | 1 | 0.8 | 0.8 | 0.8 |
| lead_at | 253 | 0.2 | 0.8 | 3.1 |
| produced_sources | 1488 | 0.3 | 0.8 | 25.3 |
| proposal_links | 2815 | 0.3 | 0.8 | 23.1 |
| related_at | 60 | 0.4 | 0.8 | 1.8 |
| revisions | 2 | 0.4 | 0.8 | 0.8 |
| span_facts | 13 | 0.2 | 0.8 | 0.8 |
| belief_lead_of | 1689 | 0.3 | 0.7 | 6.6 |
| decision_status | 144 | 0.3 | 0.7 | 10.4 |
| depends_on | 15 | 0.2 | 0.7 | 0.7 |
| neighbourhood | 61 | 0.3 | 0.7 | 2.8 |
| snap_paths | 26 | 0.4 | 0.7 | 2.0 |
| snap_person_edges | 105 | 0.3 | 0.7 | 7.3 |
| snapshot_version | 91 | 0.3 | 0.7 | 3.5 |
| source_view | 20 | 0.3 | 0.7 | 1.3 |
| strongest_member | 3538 | 0.3 | 0.7 | 17.9 |
| already_confirmed | 600 | 0.2 | 0.6 | 2.2 |
| based_on_spans | 144 | 0.3 | 0.6 | 3.4 |
| belief_all_leads | 63 | 0.3 | 0.6 | 1.0 |
| entity_name | 1465 | 0.2 | 0.6 | 8.3 |
| live_confirmations | 189 | 0.2 | 0.6 | 2.0 |
| overview_pending | 94 | 0.2 | 0.6 | 6.4 |
| proposals_about | 291 | 0.2 | 0.6 | 1.8 |
| snap_leaders | 42 | 0.2 | 0.6 | 1.1 |
| withdrawn_by | 24 | 0.3 | 0.6 | 0.7 |
| dispute_edge | 264 | 0.2 | 0.5 | 3.4 |
| latest_spans | 1 | 0.5 | 0.5 | 0.5 |
| learn_ents | 4 | 0.4 | 0.5 | 0.5 |
| pending_proposals | 10 | 0.3 | 0.5 | 0.5 |
| person_name | 1739 | 0.2 | 0.5 | 16.5 |
| rationale_spans | 144 | 0.3 | 0.5 | 3.2 |
| replaced_by | 291 | 0.2 | 0.5 | 3.5 |
| replaces_out | 291 | 0.2 | 0.5 | 3.2 |
| snap_dependents | 110 | 0.2 | 0.5 | 0.9 |
| snap_owns | 21 | 0.4 | 0.5 | 0.5 |
| snap_part_of | 21 | 0.3 | 0.5 | 0.7 |
| entity | 71 | 0.2 | 0.4 | 1.2 |
| integrity_sentinel | 1 | 0.4 | 0.4 | 0.4 |
| nodes_by_id | 61 | 0.2 | 0.4 | 0.8 |
| proposal_ends | 1068 | 0.2 | 0.4 | 2.6 |
| run_members | 2106 | 0.2 | 0.4 | 5.5 |
| snap_node_count | 21 | 0.2 | 0.4 | 0.4 |
| span_view | 20 | 0.2 | 0.4 | 0.5 |
| action_log | 10 | 0.2 | 0.3 | 0.3 |
| snap_meta | 88 | 0.2 | 0.3 | 0.8 |
| statement | 125 | 0.1 | 0.2 | 1.0 |

## FalkorDB 4.22.0, scale 10x

Graph: 26279 nodes, 69346 edges (1430 entities, 5726 assertions, 10116 spans); built in 72.6 s. Workload: 476 questions.

| Algorithm tool | n | p50 ms | p95 ms | max ms |
|---|---|---|---|---|
| critical_systems | 20 | 26.6 | 38.0 | 43.4 |
| connection_between | 20 | 3.0 | 4.2 | 4.3 |
| key_people | 20 | 128.0 | 155.6 | 158.4 |
| knowledge_gaps | 20 | 74.3 | 88.2 | 139.0 |

Snapshot rebuild, cold, 5 runs: 0.294, 0.239, 0.619, 0.275, 0.258 s.

Guarded write (`write_plan`, not a target): n 1353, p50 5.0 ms, p95 11.2 ms.

| Template | n | p50 ms | p95 ms | max ms |
|---|---|---|---|---|
| graph_edges | 29 | 52.1 | 308.1 | 347.5 |
| integrity_i1 | 1 | 233.2 | 233.2 | 233.2 |
| graph_edge_kinds | 22 | 40.6 | 211.9 | 243.0 |
| graph_nodes | 29 | 17.3 | 186.3 | 224.9 |
| experts_signals | 5 | 77.5 | 120.8 | 120.8 |
| snap_betweenness | 21 | 85.4 | 110.6 | 212.2 |
| unsupported | 1 | 99.7 | 99.7 | 99.7 |
| snapshot_touches | 7 | 62.0 | 92.4 | 92.4 |
| integrity_i5 | 1 | 76.5 | 76.5 | 76.5 |
| directory_tickets | 22 | 31.1 | 59.7 | 67.1 |
| stale_detection | 22 | 33.9 | 52.0 | 54.0 |
| directory_people | 112 | 22.1 | 38.1 | 255.9 |
| integrity_chains | 1 | 29.3 | 29.3 | 29.3 |
| all_entities | 3 | 16.9 | 24.2 | 24.2 |
| directory_decisions | 22 | 10.9 | 23.8 | 26.7 |
| overview_teams | 134 | 9.2 | 23.8 | 232.0 |
| stale_override | 22 | 12.9 | 21.8 | 67.4 |
| group_counts | 2 | 15.2 | 20.1 | 20.1 |
| directory_systems | 22 | 9.1 | 19.1 | 19.7 |
| snap_pagerank | 23 | 1.7 | 19.0 | 169.1 |
| graph_ticks | 22 | 14.5 | 18.9 | 32.3 |
| people | 20 | 13.0 | 18.2 | 23.4 |
| names | 1 | 15.1 | 15.1 | 15.1 |
| entity_names | 1772 | 6.8 | 13.5 | 470.4 |
| pending_proposals | 10 | 1.8 | 11.8 | 11.8 |
| directory_projects | 22 | 6.0 | 11.4 | 12.8 |
| snap_wcc | 21 | 8.2 | 10.2 | 98.1 |
| integrity_i11 | 1 | 8.5 | 8.5 | 8.5 |
| dispute_chains | 188 | 1.7 | 7.8 | 27.9 |
| overview_decisions | 134 | 1.8 | 5.5 | 17.2 |
| span_view | 20 | 0.4 | 4.2 | 4.5 |
| snap_owns | 21 | 2.2 | 3.4 | 3.6 |
| ticket_about | 72 | 0.6 | 3.4 | 4.7 |
| belief_all_leads | 424 | 1.5 | 3.1 | 10.6 |
| search_vector | 20 | 1.3 | 2.8 | 3.9 |
| snapshot_version | 92 | 1.2 | 2.5 | 4.2 |
| belief_out_edges | 2232 | 1.0 | 2.4 | 23.9 |
| existing_spans | 1 | 2.4 | 2.4 | 2.4 |
| link_vector | 521 | 0.8 | 2.3 | 14.9 |
| recent_actions | 50 | 0.7 | 2.3 | 3.2 |
| snap_part_of | 21 | 1.8 | 2.3 | 2.8 |
| demo_identity | 1 | 2.0 | 2.0 | 2.0 |
| confirms_of | 4 | 0.6 | 1.9 | 1.9 |
| span_details | 1664 | 0.6 | 1.8 | 23.1 |
| turn_span | 4 | 0.4 | 1.8 | 1.8 |
| session_spans | 50 | 0.7 | 1.7 | 3.5 |
| snap_leaders | 42 | 0.6 | 1.6 | 4.4 |
| decision_trace | 310 | 0.6 | 1.4 | 6.4 |
| learn_ents | 4 | 0.3 | 1.4 | 1.4 |
| turn_count | 348 | 0.4 | 1.4 | 5.7 |
| decision_status | 144 | 0.4 | 1.3 | 4.5 |
| link_fulltext | 521 | 0.5 | 1.3 | 3.2 |
| stated_by_latest | 1 | 1.3 | 1.3 | 1.3 |
| assertions_by_id | 1856 | 0.3 | 1.2 | 8.3 |
| evidence_fragment | 1506 | 0.4 | 1.2 | 8.1 |
| neighbourhood | 122 | 0.4 | 1.2 | 24.8 |
| snap_person_edges | 105 | 0.5 | 1.2 | 2.2 |
| source_exists | 2 | 0.3 | 1.2 | 1.2 |
| overview_pending | 134 | 0.3 | 1.1 | 4.4 |
| produced_assertions | 1488 | 0.4 | 1.1 | 11.3 |
| snap_paths | 26 | 0.2 | 1.1 | 3.6 |
| action_read | 1739 | 0.4 | 1.0 | 16.5 |
| chains_for_entity | 432 | 0.3 | 1.0 | 4.4 |
| entity_sources | 132 | 0.4 | 1.0 | 3.9 |
| related_at | 66 | 0.4 | 1.0 | 9.3 |
| doc_evidence | 1 | 0.9 | 0.9 | 0.9 |
| impact_dependents | 45 | 0.3 | 0.9 | 1.1 |
| link_exact | 521 | 0.3 | 0.9 | 6.7 |
| action | 1656 | 0.3 | 0.8 | 10.4 |
| current_in_chain | 50 | 0.3 | 0.8 | 1.4 |
| produced_sources | 1488 | 0.3 | 0.8 | 5.2 |
| rationale_spans | 144 | 0.3 | 0.8 | 22.2 |
| search_fulltext | 20 | 0.6 | 0.8 | 1.1 |
| based_on_spans | 144 | 0.3 | 0.7 | 6.9 |
| owner_at | 331 | 0.3 | 0.7 | 2.8 |
| proposal_links | 2817 | 0.3 | 0.7 | 38.4 |
| proposals_about | 310 | 0.2 | 0.7 | 2.7 |
| snap_dependents | 115 | 0.3 | 0.7 | 11.5 |
| snap_meta | 89 | 0.2 | 0.7 | 1.3 |
| action_log | 10 | 0.3 | 0.6 | 0.6 |
| assertion | 1928 | 0.2 | 0.6 | 7.2 |
| belief_owners_of | 2474 | 0.3 | 0.6 | 8.2 |
| depends_on | 30 | 0.2 | 0.6 | 1.6 |
| integrity_sentinel | 1 | 0.6 | 0.6 | 0.6 |
| lead_at | 343 | 0.2 | 0.6 | 40.6 |
| source_view | 20 | 0.4 | 0.6 | 1.7 |
| belief_lead_of | 2774 | 0.2 | 0.5 | 12.5 |
| decisions_affecting | 44 | 0.2 | 0.5 | 1.6 |
| entity_name | 1369 | 0.2 | 0.5 | 3.9 |
| nodes_by_id | 122 | 0.2 | 0.5 | 1.4 |
| replaces_out | 310 | 0.2 | 0.5 | 3.0 |
| span_facts | 2 | 0.3 | 0.5 | 0.5 |
| strongest_member | 3538 | 0.2 | 0.5 | 4.8 |
| withdrawn_by | 24 | 0.3 | 0.5 | 1.0 |
| already_confirmed | 600 | 0.2 | 0.4 | 2.6 |
| disputed_run | 1274 | 0.2 | 0.4 | 5.0 |
| latest_spans | 1 | 0.4 | 0.4 | 0.4 |
| live_confirmations | 1274 | 0.2 | 0.4 | 3.2 |
| person_name | 1739 | 0.2 | 0.4 | 5.5 |
| proposal_ends | 1068 | 0.2 | 0.4 | 12.3 |
| replaced_by | 310 | 0.2 | 0.4 | 4.0 |
| run_members | 4220 | 0.2 | 0.4 | 11.5 |
| statement | 1241 | 0.2 | 0.4 | 9.8 |
| dispute_edge | 2640 | 0.2 | 0.3 | 12.6 |
| entity | 132 | 0.2 | 0.3 | 2.2 |
| revisions | 2 | 0.3 | 0.3 | 0.3 |
| snap_node_count | 21 | 0.3 | 0.3 | 0.3 |

### PROFILE graph_edges (4.22.0, 10x)

```
Results | Records produced: 2746, Execution time: 0.117389 ms
    Project | Records produced: 2746, Execution time: 1.625531 ms
        Filter | Records produced: 2746, Execution time: 3.646743 ms
            Conditional Traverse | (a)-[e]->(b:Entity) | Records produced: 3041, Execution time: 20.602476 ms
                Node By Label Scan | (a:Entity) | Records produced: 1574, Execution time: 0.106193 ms
```

### PROFILE integrity_i1 (4.22.0, 10x)

```
Results | Records produced: 3531, Execution time: 0.150241 ms
    Aggregate | Records produced: 3531, Execution time: 32.626862 ms
        Filter | Records produced: 4361, Execution time: 4.721769 ms
            Node By Label Scan | (a:Assertion) | Records produced: 7511, Execution time: 0.312620 ms
```

### PROFILE graph_edge_kinds (4.22.0, 10x)

```
Results | Records produced: 2746, Execution time: 0.113503 ms
    Aggregate | Records produced: 2746, Execution time: 10.734507 ms
        Filter | Records produced: 3536, Execution time: 1.002421 ms
            Conditional Traverse | (a)-[ev:EVIDENCED_BY]->(s:Span) | Records produced: 3886, Execution time: 6.297250 ms
                Node By Index Scan | (a:Assertion) | Records produced: 3526, Execution time: 20.602644 ms
```

### PROFILE graph_nodes (4.22.0, 10x)

```
Results | Records produced: 1574, Execution time: 0.066410 ms
    Project | Records produced: 1574, Execution time: 0.588366 ms
        Node By Label Scan | (n:Entity) | Records produced: 1574, Execution time: 0.056505 ms
```

### PROFILE experts_signals (4.22.0, 10x)

```
Results | Records produced: 1, Execution time: 0.002500 ms
    Aggregate | Records produced: 1, Execution time: 1.141163 ms
        Optional Conditional Traverse | (d)-[db:DECIDED_BY]->(p5:Person) | Records produced: 1, Execution time: 0.240623 ms
            Optional Conditional Traverse | (d)-[af:AFFECTS]->(d) | Records produced: 1, Execution time: 0.283750 ms
                Aggregate | Records produced: 1, Execution time: 74.732961 ms
                    Apply | Records produced: 2520, Execution time: 0.223690 ms
                        Aggregate | Records produced: 1, Execution time: 1.068366 ms
                            Apply | Records produced: 120, Execution time: 0.013135 ms
                                Aggregate | Records produced: 1, Execution time: 0.054417 ms
                                    Apply | Records produced: 1, Execution time: 0.003208 ms
                                        Aggregate | Records produced: 1, Execution time: 0.065291 ms
                                            Apply | Records produced: 44, Execution time: 0.004465 ms
                                                Node By Index Scan | (x:Entity) | Records produced: 1, Execution time: 0.022291 ms
                                                Optional | Records produced: 44, Execution time: 0.002539 ms
                                                    Conditional Traverse | (s)->(p:Person) | Records produced: 44, Execution time: 0.142581 ms
                                                        Filter | Records produced: 64, Execution time: 0.015211 ms
                                                            Conditional Traverse | (s)->(s) | Records produced: 66, Execution time: 0.124537 ms
                                                                Argument | Records produced: 1, Execution time: 0.000000 ms
                                        Optional | Records produced: 1, Execution time: 0.000124 ms
                                            Filter | Records produced: 0, Execution time: 0.000168 ms
                                                Conditional Traverse | (p2)-[r:OWNS|:WORKS_ON|:LEADS]->(p2) | Records produced: 0, Execution time: 0.054416 ms
                                                    Argument | Records produced: 1, Execution time: 0.000083 ms
                                Optional | Records produced: 120, Execution time: 0.005001 ms
                                    Filter | Records produced: 120, Execution time: 0.054654 ms
                                        Edge By Index Scan | [l:LEADS] | Records produced: 120, Execution time: 0.116382 ms
                                            Filter | Records produced: 1, Execution time: 0.013333 ms
                                                Edge By Index Scan | [o:OWNS] | Records produced: 1, Execution time: 0.019917 ms
                                                    Argument | Records produced: 1, Execution time: 0.000041 ms
                        Optional | Records produced: 2520, Execution time: 0.131004 ms
                            Filter | Records produced: 2520, Execution time: 1.310673 ms
                                Edge By Index Scan | [asg:ASSIGNED_TO] | Records produced: 2940, Execution time: 1.929179 ms
                                    Filter | Records produced: 7, Execution time: 1.999742 ms
                                        Edge By Index Scan | [ab:ABOUT] | Records produced: 7, Execution time: 0.065123 ms
                                            Argument | Records produced: 1, Execution time: 0.000000 ms
```

## Templates not exercised by the workload

action_draft, action_evidence, action_targets, any_confirmed, any_person, belief_parent_of, belief_primary_team, chain_meta, confirmed_proposals, confirmed_targets, draft_decision, draft_status, graph_mentioned, owner_inherited, owner_previous, past_belief_members, past_belief_run, paths_between, session
