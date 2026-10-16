# ABORTED after 27 answers: drafter error rate 3/23

Resume with the same command and cache.

# Answer layer

Fixed sample of up to 10 questions per category per seed; seeds [1, 2, 3].

| Metric | D (graph agent) |
|---|---|
| entity_match | 1.000 (n=24) |
| entity_f1 | 0.664 (n=22) |
| citation_precision | 0.773 (n=22) |
| citation_recall | 0.955 (n=22) |
| v2_pass | 0.958 (n=24) |
| v3_pass | 1.000 (n=24) |
| dispute_disclosure | 1.000 (n=3) |
| stale_error | 0.000 (n=1) |
| proposal_labelling | 1.000 (n=2) |
| proposal_as_current | 0.000 (n=2) |
| action_cited | 1.000 (n=4) |
| action_in_pack | 1.000 (n=4) |
| history_judge | 0.750 (n=8) |
| abstention P/R (D) | 1.00 / 1.00 |
| plan_ms p50/p95 (D) | 24 / 2308 |
| tools_ms p50/p95 (D) | 29 / 92 |
| draft_ms p50/p95 (D) | 3124 / 7180 |
| verify_ms p50/p95 (D) | 0 / 3638 |
| latency_ms p50/p95 (D) | 3962 / 10119 |
| draft citations, final (D) | 0 (must be 0) |
| judge agreement (D) | 0.75 (n=4) |

## Per category, variant D

| Category | n | abstained | entity_match | entity_f1 | citation_recall | dispute_disclosure | stale_error | proposal_labelling | action_cited | action_in_pack | aggregate_acceptable | aggregate_correct | history_judge |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 single-hop | 3 | 0 | 1.000 (n=3) | 1.000 (n=3) | 1.000 (n=3) | — | — | — | — | — | — | — | — |
| 2 multi-hop | 3 | 0 | 1.000 (n=3) | 0.622 (n=3) | 1.000 (n=3) | — | — | — | — | — | — | — | — |
| 3 ownership | 3 | 0 | 1.000 (n=3) | 0.667 (n=3) | 1.000 (n=3) | — | — | — | — | — | — | — | — |
| 4 decision trace | 3 | 0 | 1.000 (n=3) | 0.667 (n=3) | 1.000 (n=3) | — | — | — | — | — | — | — | — |
| 4-pending pending draft | 2 | 0 | 1.000 (n=2) | 0.000 (n=2) | — | — | — | 1.000 (n=2) | 1.000 (n=2) | 1.000 (n=2) | — | — | — |
| 5 stale fact | 3 | 0 | 1.000 (n=3) | 0.778 (n=3) | 1.000 (n=3) | — | 0.000 (n=1) | — | — | — | — | — | 1.000 (n=3) |
| 6 unanswerable | 3 | 3 | — | — | — | — | — | — | — | — | — | — | — |
| 7 past belief | 2 | 0 | 1.000 (n=2) | 0.500 (n=2) | 0.500 (n=2) | — | — | — | 1.000 (n=2) | 1.000 (n=2) | — | — | 0.000 (n=2) |
| 8 disputed | 3 | 0 | 1.000 (n=3) | 0.800 (n=3) | 1.000 (n=3) | 1.000 (n=3) | — | — | — | — | — | — | 1.000 (n=3) |
| 9 session memory | 2 | 0 | 1.000 (n=2) | — | 1.000 (n=2) | — | — | — | — | — | — | — | — |

Category 7 by phrasing template (D): t0: action_cited=1.000 (n=1), entity=1.000 (n=1); t2: action_cited=1.000 (n=1), entity=1.000 (n=1)

## Setup scripts (scratch graphs, torn down)

- seed 1 `eval_scratch_1_f996c5f3a9`: 6 steps, 1 questions, 9.5 s
- seed 1 `eval_scratch_1_9ebf485ae0`: 24 steps, 1 questions, 10.6 s
- seed 1 `eval_scratch_1_97d170e155`: 0 steps, 1 questions, 10.1 s
- seed 2 `eval_scratch_2_e096d2892e`: 6 steps, 1 questions, 10.6 s
- seed 2 `eval_scratch_2_570bb7bcd5`: 40 steps, 1 questions, 10.9 s
- seed 2 `eval_scratch_2_97d170e155`: 0 steps, 1 questions, 10.7 s

## Run report

| Rate | Value |
|---|---|
| deterministic fallback | 2 of 17 answers the drafter should have written |
| escalation | 0 of 27 |
| checker blocked | 0 of 27 |

Served: drafter: poolside/laguna-xs-2.1 via Poolside (15); planner: poolside/laguna-xs-2.1 via Poolside (8)
