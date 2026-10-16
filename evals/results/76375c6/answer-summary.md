# Answer layer

Fixed sample of up to 10 questions per category per seed; seeds [1, 2, 3].

| Metric | D (graph agent) |
|---|---|
| entity_match | 0.922 (n=296) |
| entity_f1 | 0.486 (n=243) |
| citation_precision | 0.742 (n=240) |
| citation_recall | 0.956 (n=240) |
| v2_pass | 1.000 (n=303) |
| v3_pass | 1.000 (n=303) |
| dispute_disclosure | 1.000 (n=30) |
| stale_error | 0.000 (n=22) |
| proposal_labelling | 1.000 (n=30) |
| proposal_as_current | 0.000 (n=30) |
| action_cited | 0.952 (n=63) |
| action_in_pack | 1.000 (n=63) |
| aggregate_acceptable | 1.000 (n=33) |
| aggregate_correct | 1.000 (n=33) |
| history_judge | 0.889 (n=90) |
| abstention P/R (D) | 1.00 / 1.00 |
| plan_ms p50/p95 (D) | 128 / 408 |
| tools_ms p50/p95 (D) | 45 / 228 |
| draft_ms p50/p95 (D) | 71 / 236 |
| verify_ms p50/p95 (D) | 0 / 0 |
| latency_ms p50/p95 (D) | 277 / 689 |
| draft citations, final (D) | 0 (must be 0) |
| judge agreement (D) | 0.56 (n=34) |

## Per category, variant D

| Category | n | abstained | entity_match | entity_f1 | citation_recall | dispute_disclosure | stale_error | proposal_labelling | action_cited | action_in_pack | aggregate_acceptable | aggregate_correct | history_judge |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 single-hop | 30 | 0 | 1.000 (n=30) | 0.500 (n=30) | 0.933 (n=30) | — | — | — | — | — | — | — | — |
| 2 multi-hop | 30 | 0 | 1.000 (n=30) | 0.560 (n=30) | 1.000 (n=30) | — | — | — | — | — | — | — | — |
| 3 ownership | 30 | 0 | 1.000 (n=30) | 0.520 (n=30) | 0.983 (n=30) | — | — | — | — | — | — | — | — |
| 4 decision trace | 30 | 0 | 1.000 (n=30) | 0.356 (n=30) | 1.000 (n=30) | — | — | — | — | — | — | — | — |
| 4-pending pending draft | 30 | 0 | 1.000 (n=30) | 0.000 (n=30) | — | — | — | 1.000 (n=30) | 1.000 (n=30) | 1.000 (n=30) | — | — | — |
| 5 stale fact | 30 | 0 | 1.000 (n=30) | 0.822 (n=30) | 1.000 (n=30) | — | 0.000 (n=22) | — | — | — | — | — | 0.967 (n=30) |
| 6 unanswerable | 30 | 30 | 0.000 (n=8) | — | — | — | — | — | — | — | — | — | — |
| 7 past belief | 30 | 0 | 1.000 (n=30) | 0.294 (n=30) | 0.733 (n=30) | — | — | — | 1.000 (n=30) | 1.000 (n=30) | — | — | 0.767 (n=30) |
| 8 disputed | 30 | 0 | 1.000 (n=30) | 0.860 (n=30) | 1.000 (n=30) | 1.000 (n=30) | — | — | — | — | — | — | 0.933 (n=30) |
| 9 session memory | 30 | 0 | 1.000 (n=30) | — | 1.000 (n=30) | — | — | — | 0.000 (n=3) | 1.000 (n=3) | — | — | — |
| 10 outside templates | 30 | 0 | 0.000 (n=15) | — | — | — | — | — | — | — | 1.000 (n=30) | 1.000 (n=30) | — |
| 11 graph algorithms | 3 | 0 | 1.000 (n=3) | 0.250 (n=3) | — | — | — | — | — | — | 1.000 (n=3) | 1.000 (n=3) | — |

Category 10 outcomes (D): correct=33; answers using an unverified_path claim: 0

Category 7 by phrasing template (D): t0: action_cited=1.000 (n=10), entity=1.000 (n=10); t1: action_cited=1.000 (n=11), entity=1.000 (n=11); t2: action_cited=1.000 (n=9), entity=1.000 (n=9)

## Setup scripts (scratch graphs, torn down)

- seed 1 `eval_scratch_1_f996c5f3a9`: 6 steps, 10 questions, 20.1 s
- seed 1 `eval_scratch_1_9ebf485ae0`: 24 steps, 10 questions, 14.4 s
- seed 1 `eval_scratch_1_97d170e155`: 0 steps, 10 questions, 43.6 s
- seed 2 `eval_scratch_2_e096d2892e`: 6 steps, 10 questions, 37.7 s
- seed 2 `eval_scratch_2_570bb7bcd5`: 40 steps, 10 questions, 32.2 s
- seed 2 `eval_scratch_2_97d170e155`: 0 steps, 10 questions, 24.1 s
- seed 3 `eval_scratch_3_02bc3eb76c`: 6 steps, 10 questions, 13.6 s
- seed 3 `eval_scratch_3_58e4bab760`: 31 steps, 10 questions, 14.2 s
- seed 3 `eval_scratch_3_97d170e155`: 0 steps, 10 questions, 13.3 s
