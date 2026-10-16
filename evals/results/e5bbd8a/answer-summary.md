# Answer layer

Fixed sample of up to 10 questions per category per seed; seeds [1, 2, 3].

| Metric | D (graph agent) |
|---|---|
| entity_match | 0.902 (n=321) |
| entity_f1 | 0.466 (n=268) |
| citation_precision | 0.745 (n=240) |
| citation_recall | 0.921 (n=240) |
| v2_pass | 0.998 (n=335) |
| v3_pass | 0.999 (n=335) |
| dispute_disclosure | 0.767 (n=30) |
| stale_error | 0.000 (n=22) |
| proposal_labelling | 1.000 (n=30) |
| proposal_as_current | 0.000 (n=30) |
| action_cited | 0.952 (n=63) |
| action_in_pack | 1.000 (n=63) |
| aggregate_acceptable | 1.000 (n=58) |
| aggregate_correct | 1.000 (n=58) |
| history_judge | 0.878 (n=90) |
| abstention P/R (D) | 1.00 / 0.77 |
| plan_ms p50/p95 (D) | 0 / 1154 |
| tools_ms p50/p95 (D) | 48 / 122 |
| draft_ms p50/p95 (D) | 1 / 7496 |
| verify_ms p50/p95 (D) | 611 / 4096 |
| latency_ms p50/p95 (D) | 2751 / 10713 |
| draft citations, final (D) | 0 (must be 0) |
| judge agreement (D) | 0.71 (n=35) |

## Per category, variant D

| Category | n | abstained | entity_match | entity_f1 | citation_recall | dispute_disclosure | stale_error | proposal_labelling | action_cited | action_in_pack | aggregate_acceptable | aggregate_correct | history_judge |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 single-hop | 30 | 0 | 1.000 (n=30) | 0.500 (n=30) | 0.933 (n=30) | — | — | — | — | — | — | — | — |
| 2 multi-hop | 30 | 0 | 1.000 (n=30) | 0.571 (n=30) | 1.000 (n=30) | — | — | — | — | — | — | — | — |
| 3 ownership | 30 | 0 | 1.000 (n=30) | 0.549 (n=30) | 0.983 (n=30) | — | — | — | — | — | — | — | — |
| 4 decision trace | 30 | 0 | 1.000 (n=30) | 0.356 (n=30) | 1.000 (n=30) | — | — | — | — | — | — | — | — |
| 4-pending pending draft | 30 | 0 | 1.000 (n=30) | 0.000 (n=30) | — | — | — | 1.000 (n=30) | 1.000 (n=30) | 1.000 (n=30) | — | — | — |
| 5 stale fact | 30 | 0 | 0.833 (n=30) | 0.656 (n=30) | 0.833 (n=30) | — | 0.000 (n=22) | — | — | — | — | — | 0.833 (n=30) |
| 6 unanswerable | 30 | 23 | 0.000 (n=8) | — | — | — | — | — | — | — | — | — | — |
| 7 past belief | 30 | 0 | 1.000 (n=30) | 0.294 (n=30) | 0.733 (n=30) | — | — | — | 1.000 (n=30) | 1.000 (n=30) | — | — | 0.800 (n=30) |
| 8 disputed | 30 | 0 | 0.883 (n=30) | 0.790 (n=30) | 0.883 (n=30) | 0.767 (n=30) | — | — | — | — | — | — | 1.000 (n=30) |
| 9 session memory | 30 | 0 | 1.000 (n=30) | — | 1.000 (n=30) | — | — | — | 0.000 (n=3) | 1.000 (n=3) | — | — | — |
| 10 outside templates | 30 | 0 | 0.000 (n=15) | — | — | — | — | — | — | — | 1.000 (n=30) | 1.000 (n=30) | — |
| 11 graph algorithms | 28 | 0 | 1.000 (n=28) | 0.476 (n=28) | — | — | — | — | — | — | 1.000 (n=28) | 1.000 (n=28) | — |

Category 10 outcomes (D): correct=58; answers using an unverified_path claim: 0

Category 7 by phrasing template (D): t0: action_cited=1.000 (n=10), entity=1.000 (n=10); t1: action_cited=1.000 (n=11), entity=1.000 (n=11); t2: action_cited=1.000 (n=9), entity=1.000 (n=9)

## Setup scripts (scratch graphs, torn down)

- seed 1 `eval_scratch_1_f996c5f3a9`: 6 steps, 10 questions, 14.0 s
- seed 1 `eval_scratch_1_9ebf485ae0`: 24 steps, 10 questions, 10.6 s
- seed 1 `eval_scratch_1_97d170e155`: 0 steps, 10 questions, 10.5 s
- seed 2 `eval_scratch_2_e096d2892e`: 6 steps, 10 questions, 9.3 s
- seed 2 `eval_scratch_2_570bb7bcd5`: 40 steps, 10 questions, 10.4 s
- seed 2 `eval_scratch_2_97d170e155`: 0 steps, 10 questions, 8.4 s
- seed 3 `eval_scratch_3_02bc3eb76c`: 6 steps, 10 questions, 9.0 s
- seed 3 `eval_scratch_3_58e4bab760`: 31 steps, 10 questions, 9.4 s
- seed 3 `eval_scratch_3_97d170e155`: 0 steps, 10 questions, 9.9 s

## Run report

| Rate | Value |
|---|---|
| deterministic fallback | 0 of 180 answers the drafter should have written |
| escalation | 0 of 358 |
| checker blocked | 107 of 358 |

Served: checker: nace-ai/drex-v2.0 via DeepInfra (10); checker: typesafe/jev-1.14 via TypeSafe (325); drafter: anthropic/claude-haiku-5.5 via Azure (1); drafter: deepseek/deepseek-v4.1-flash via DeepInfra (124); planner: deepseek/deepseek-v4.1-flash via DeepInfra (90)
