# Answer layer

Fixed sample of up to 10 questions per category per seed; seeds [1, 2, 3].

| Metric | D (graph agent) |
|---|---|
| entity_match | 0.981 (n=27) |
| entity_f1 | 0.591 (n=24) |
| citation_precision | 0.777 (n=24) |
| citation_recall | 0.938 (n=24) |
| v2_pass | 0.969 (n=27) |
| v3_pass | 1.000 (n=27) |
| dispute_disclosure | 0.667 (n=3) |
| stale_error | 0.000 (n=1) |
| proposal_labelling | 1.000 (n=3) |
| proposal_as_current | 0.000 (n=3) |
| action_cited | 1.000 (n=6) |
| action_in_pack | 1.000 (n=6) |
| history_judge | 0.889 (n=9) |
| abstention P/R (D) | 1.00 / 1.00 |
| plan_ms p50/p95 (D) | 30 / 2296 |
| tools_ms p50/p95 (D) | 40 / 136 |
| draft_ms p50/p95 (D) | 2918 / 7984 |
| verify_ms p50/p95 (D) | 552 / 4415 |
| latency_ms p50/p95 (D) | 4350 / 10768 |
| draft citations, final (D) | 0 (must be 0) |
| judge agreement (D) | 1.00 (n=3) |

## Per category, variant D

| Category | n | abstained | entity_match | entity_f1 | citation_recall | dispute_disclosure | stale_error | proposal_labelling | action_cited | action_in_pack | aggregate_acceptable | aggregate_correct | history_judge |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 single-hop | 3 | 0 | 1.000 (n=3) | 1.000 (n=3) | 1.000 (n=3) | — | — | — | — | — | — | — | — |
| 2 multi-hop | 3 | 0 | 1.000 (n=3) | 0.586 (n=3) | 1.000 (n=3) | — | — | — | — | — | — | — | — |
| 3 ownership | 3 | 0 | 1.000 (n=3) | 0.667 (n=3) | 1.000 (n=3) | — | — | — | — | — | — | — | — |
| 4 decision trace | 3 | 0 | 1.000 (n=3) | 0.667 (n=3) | 1.000 (n=3) | — | — | — | — | — | — | — | — |
| 4-pending pending draft | 3 | 0 | 1.000 (n=3) | 0.000 (n=3) | — | — | — | 1.000 (n=3) | 1.000 (n=3) | 1.000 (n=3) | — | — | — |
| 5 stale fact | 3 | 0 | 1.000 (n=3) | 0.778 (n=3) | 1.000 (n=3) | — | 0.000 (n=1) | — | — | — | — | — | 1.000 (n=3) |
| 6 unanswerable | 3 | 3 | — | — | — | — | — | — | — | — | — | — | — |
| 7 past belief | 3 | 0 | 1.000 (n=3) | 0.333 (n=3) | 0.667 (n=3) | — | — | — | 1.000 (n=3) | 1.000 (n=3) | — | — | 0.667 (n=3) |
| 8 disputed | 3 | 0 | 0.833 (n=3) | 0.700 (n=3) | 0.833 (n=3) | 0.667 (n=3) | — | — | — | — | — | — | 1.000 (n=3) |
| 9 session memory | 3 | 0 | 1.000 (n=3) | — | 1.000 (n=3) | — | — | — | — | — | — | — | — |

Category 7 by phrasing template (D): t0: action_cited=1.000 (n=1), entity=1.000 (n=1); t1: action_cited=1.000 (n=1), entity=1.000 (n=1); t2: action_cited=1.000 (n=1), entity=1.000 (n=1)

## Setup scripts (scratch graphs, torn down)

- seed 1 `eval_scratch_1_f996c5f3a9`: 6 steps, 1 questions, 8.4 s
- seed 1 `eval_scratch_1_9ebf485ae0`: 24 steps, 1 questions, 8.4 s
- seed 1 `eval_scratch_1_97d170e155`: 0 steps, 1 questions, 11.0 s
- seed 2 `eval_scratch_2_e096d2892e`: 6 steps, 1 questions, 10.3 s
- seed 2 `eval_scratch_2_570bb7bcd5`: 40 steps, 1 questions, 10.5 s
- seed 2 `eval_scratch_2_97d170e155`: 0 steps, 1 questions, 11.2 s
- seed 3 `eval_scratch_3_02bc3eb76c`: 6 steps, 1 questions, 10.3 s
- seed 3 `eval_scratch_3_58e4bab760`: 31 steps, 1 questions, 9.5 s
- seed 3 `eval_scratch_3_97d170e155`: 0 steps, 1 questions, 9.1 s

## Run report

| Rate | Value |
|---|---|
| deterministic fallback | 0 of 18 answers the drafter should have written |
| escalation | 0 of 30 |
| checker blocked | 5 of 30 |

Served: checker: typesafe/jev-1.14 via TypeSafe (27); drafter: poolside/laguna-xs-2.1 via Poolside (16); planner: poolside/laguna-xs-2.1 via Poolside (9)
