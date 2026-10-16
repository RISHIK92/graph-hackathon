# ABORTED after 17 answers: drafter error rate 1/14

Resume with the same command and cache.

# Answer layer

Fixed sample of up to 10 questions per category per seed; seeds [1, 2, 3].

| Metric | D (graph agent) |
|---|---|
| entity_match | 1.000 (n=15) |
| entity_f1 | 0.693 (n=14) |
| citation_precision | 0.792 (n=14) |
| citation_recall | 0.964 (n=14) |
| v2_pass | 0.967 (n=15) |
| v3_pass | 1.000 (n=15) |
| dispute_disclosure | 1.000 (n=2) |
| proposal_labelling | 1.000 (n=1) |
| proposal_as_current | 0.000 (n=1) |
| action_cited | 1.000 (n=2) |
| action_in_pack | 1.000 (n=2) |
| history_judge | 1.000 (n=5) |
| abstention P/R (D) | 1.00 / 1.00 |
| plan_ms p50/p95 (D) | 27 / 2767 |
| tools_ms p50/p95 (D) | 39 / 80 |
| draft_ms p50/p95 (D) | 2998 / 7165 |
| verify_ms p50/p95 (D) | 574 / 5419 |
| latency_ms p50/p95 (D) | 5533 / 13407 |
| draft citations, final (D) | 0 (must be 0) |
| judge agreement (D) | 1.00 (n=2) |

## Per category, variant D

| Category | n | abstained | entity_match | entity_f1 | citation_recall | dispute_disclosure | stale_error | proposal_labelling | action_cited | action_in_pack | aggregate_acceptable | aggregate_correct | history_judge |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 single-hop | 2 | 0 | 1.000 (n=2) | 1.000 (n=2) | 1.000 (n=2) | — | — | — | — | — | — | — | — |
| 2 multi-hop | 2 | 0 | 1.000 (n=2) | 0.633 (n=2) | 1.000 (n=2) | — | — | — | — | — | — | — | — |
| 3 ownership | 2 | 0 | 1.000 (n=2) | 0.667 (n=2) | 1.000 (n=2) | — | — | — | — | — | — | — | — |
| 4 decision trace | 2 | 0 | 1.000 (n=2) | 0.667 (n=2) | 1.000 (n=2) | — | — | — | — | — | — | — | — |
| 4-pending pending draft | 1 | 0 | 1.000 (n=1) | 0.000 (n=1) | — | — | — | 1.000 (n=1) | 1.000 (n=1) | 1.000 (n=1) | — | — | — |
| 5 stale fact | 2 | 0 | 1.000 (n=2) | 0.833 (n=2) | 1.000 (n=2) | — | — | — | — | — | — | — | 1.000 (n=2) |
| 6 unanswerable | 2 | 2 | — | — | — | — | — | — | — | — | — | — | — |
| 7 past belief | 1 | 0 | 1.000 (n=1) | 0.500 (n=1) | 0.500 (n=1) | — | — | — | 1.000 (n=1) | 1.000 (n=1) | — | — | 1.000 (n=1) |
| 8 disputed | 2 | 0 | 1.000 (n=2) | 0.800 (n=2) | 1.000 (n=2) | 1.000 (n=2) | — | — | — | — | — | — | 1.000 (n=2) |
| 9 session memory | 1 | 0 | 1.000 (n=1) | — | 1.000 (n=1) | — | — | — | — | — | — | — | — |

Category 7 by phrasing template (D): t2: action_cited=1.000 (n=1), entity=1.000 (n=1)

## Setup scripts (scratch graphs, torn down)

- seed 1 `eval_scratch_1_f996c5f3a9`: 6 steps, 1 questions, 9.9 s
- seed 1 `eval_scratch_1_9ebf485ae0`: 24 steps, 1 questions, 10.7 s
- seed 1 `eval_scratch_1_97d170e155`: 0 steps, 1 questions, 11.2 s

## Run report

| Rate | Value |
|---|---|
| deterministic fallback | 0 of 11 answers the drafter should have written |
| escalation | 0 of 17 |
| checker blocked | 3 of 17 |

Served: checker: typesafe/jev-1.14 via TypeSafe (15); drafter: poolside/laguna-xs-2.1 via Poolside (9); planner: poolside/laguna-xs-2.1 via Poolside (5)
