# Answer layer

Fixed sample of up to 10 questions per category per seed; seeds [1, 2, 3].

| Metric | D (graph agent) |
|---|---|
| entity_match | 0.920 (n=293) |
| entity_f1 | 0.470 (n=240) |
| citation_precision | 0.700 (n=240) |
| citation_recall | 0.960 (n=240) |
| v2_pass | 0.995 (n=304) |
| v3_pass | 1.000 (n=304) |
| dispute_disclosure | 0.967 (n=30) |
| stale_error | 0.000 (n=22) |
| proposal_labelling | 1.000 (n=30) |
| proposal_as_current | 0.000 (n=30) |
| action_cited | 0.952 (n=63) |
| action_in_pack | 1.000 (n=63) |
| aggregate_acceptable | 1.000 (n=30) |
| aggregate_correct | 1.000 (n=30) |
| history_judge | 0.778 (n=90) |
| abstention P/R (D) | 1.00 / 0.87 |
| plan_ms p50/p95 (D) | 2 / 27 |
| tools_ms p50/p95 (D) | 33 / 94 |
| draft_ms p50/p95 (D) | 1 / 6515 |
| verify_ms p50/p95 (D) | 0 / 1 |
| latency_ms p50/p95 (D) | 88 / 7717 |
| draft citations, final (D) | 0 (must be 0) |

## Per category, variant D

| Category | n | abstained | entity_match | entity_f1 | citation_recall | dispute_disclosure | stale_error | proposal_labelling | action_cited | action_in_pack | aggregate_acceptable | aggregate_correct | history_judge |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 single-hop | 30 | 0 | 1.000 (n=30) | 0.500 (n=30) | 1.000 (n=30) | — | — | — | — | — | — | — | — |
| 2 multi-hop | 30 | 0 | 1.000 (n=30) | 0.546 (n=30) | 0.960 (n=30) | — | — | — | — | — | — | — | — |
| 3 ownership | 30 | 0 | 1.000 (n=30) | 0.520 (n=30) | 1.000 (n=30) | — | — | — | — | — | — | — | — |
| 4 decision trace | 30 | 0 | 1.000 (n=30) | 0.227 (n=30) | 1.000 (n=30) | — | — | — | — | — | — | — | — |
| 4-pending pending draft | 30 | 0 | 1.000 (n=30) | 0.000 (n=30) | — | — | — | 1.000 (n=30) | 1.000 (n=30) | 1.000 (n=30) | — | — | — |
| 5 stale fact | 30 | 0 | 1.000 (n=30) | 0.822 (n=30) | 1.000 (n=30) | — | 0.000 (n=22) | — | — | — | — | — | 1.000 (n=30) |
| 6 unanswerable | 30 | 26 | 0.000 (n=8) | — | — | — | — | — | — | — | — | — | — |
| 7 past belief | 30 | 0 | 1.000 (n=30) | 0.294 (n=30) | 0.733 (n=30) | — | — | — | 1.000 (n=30) | 1.000 (n=30) | — | — | 0.633 (n=30) |
| 8 disputed | 30 | 0 | 0.983 (n=30) | 0.850 (n=30) | 0.983 (n=30) | 0.967 (n=30) | — | — | — | — | — | — | 0.700 (n=30) |
| 9 session memory | 30 | 0 | 1.000 (n=30) | — | 1.000 (n=30) | — | — | — | 0.000 (n=3) | 1.000 (n=3) | — | — | — |
| 10 outside templates | 30 | 0 | 0.000 (n=15) | — | — | — | — | — | — | — | 1.000 (n=30) | 1.000 (n=30) | — |

Category 10 outcomes (D): correct=30; answers using an unverified_path claim: 0

Category 7 by phrasing template (D): t0: action_cited=1.000 (n=10), entity=1.000 (n=10); t1: action_cited=1.000 (n=11), entity=1.000 (n=11); t2: action_cited=1.000 (n=9), entity=1.000 (n=9)

## Setup scripts (scratch graphs, torn down)

- seed 1 `eval_scratch_1_f996c5f3a9`: 6 steps, 10 questions, 12.2 s
- seed 1 `eval_scratch_1_9ebf485ae0`: 24 steps, 10 questions, 10.9 s
- seed 1 `eval_scratch_1_97d170e155`: 0 steps, 10 questions, 10.4 s
- seed 2 `eval_scratch_2_e096d2892e`: 6 steps, 10 questions, 11.6 s
- seed 2 `eval_scratch_2_570bb7bcd5`: 40 steps, 10 questions, 11.4 s
- seed 2 `eval_scratch_2_97d170e155`: 0 steps, 10 questions, 11.4 s
- seed 3 `eval_scratch_3_02bc3eb76c`: 6 steps, 10 questions, 10.7 s
- seed 3 `eval_scratch_3_58e4bab760`: 31 steps, 10 questions, 11.3 s
- seed 3 `eval_scratch_3_97d170e155`: 0 steps, 10 questions, 12.0 s
