# Answer layer

Fixed sample of up to 10 questions per category per seed; seeds [1, 2, 3].

| Metric | D (graph agent) |
|---|---|
| entity_match | 0.887 (n=293) |
| entity_f1 | 0.400 (n=266) |
| citation_precision | 0.591 (n=227) |
| citation_recall | 0.810 (n=240) |
| v2_pass | 0.984 (n=282) |
| v3_pass | 1.000 (n=282) |
| dispute_disclosure | 0.867 (n=30) |
| stale_error | 0.000 (n=22) |
| proposal_labelling | 0.800 (n=30) |
| proposal_as_current | 0.000 (n=30) |
| action_cited | 0.857 (n=63) |
| action_in_pack | 0.905 (n=63) |
| aggregate_acceptable | 0.767 (n=30) |
| aggregate_correct | 0.700 (n=30) |
| history_judge | 0.700 (n=90) |
| abstention P/R (D) | 0.60 / 1.00 |
| plan_ms p50/p95 (D) | 744 / 3475 |
| tools_ms p50/p95 (D) | 64 / 268 |
| draft_ms p50/p95 (D) | 4121 / 14085 |
| verify_ms p50/p95 (D) | 0 / 12428 |
| latency_ms p50/p95 (D) | 6150 / 34986 |
| draft citations, final (D) | 0 (must be 0) |

## Per category, variant D

| Category | n | abstained | entity_match | entity_f1 | citation_recall | dispute_disclosure | stale_error | proposal_labelling | action_cited | action_in_pack | aggregate_acceptable | aggregate_correct | history_judge |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 single-hop | 30 | 0 | 1.000 (n=30) | 0.500 (n=30) | 1.000 (n=30) | — | — | — | — | — | — | — | — |
| 2 multi-hop | 30 | 0 | 1.000 (n=30) | 0.546 (n=30) | 0.917 (n=30) | — | — | — | — | — | — | — | — |
| 3 ownership | 30 | 0 | 1.000 (n=30) | 0.522 (n=30) | 1.000 (n=30) | — | — | — | — | — | — | — | — |
| 4 decision trace | 30 | 0 | 1.000 (n=30) | 0.141 (n=30) | 0.467 (n=30) | — | — | — | — | — | — | — | — |
| 4-pending pending draft | 30 | 5 | 0.833 (n=30) | 0.000 (n=25) | — | — | — | 0.800 (n=30) | 0.800 (n=30) | 0.800 (n=30) | — | — | — |
| 5 stale fact | 30 | 3 | 0.900 (n=30) | 0.802 (n=27) | 0.900 (n=30) | — | 0.000 (n=22) | — | — | — | — | — | 0.867 (n=30) |
| 6 unanswerable | 30 | 30 | 0.000 (n=8) | — | — | — | — | — | — | — | — | — | — |
| 7 past belief | 30 | 0 | 1.000 (n=30) | 0.294 (n=30) | 0.733 (n=30) | — | — | — | 1.000 (n=30) | 1.000 (n=30) | — | — | 0.600 (n=30) |
| 8 disputed | 30 | 0 | 0.933 (n=30) | 0.820 (n=30) | 0.933 (n=30) | 0.867 (n=30) | — | — | — | — | — | — | 0.633 (n=30) |
| 9 session memory | 30 | 10 | 0.533 (n=30) | 0.000 (n=20) | 0.533 (n=30) | — | — | — | 0.000 (n=3) | 1.000 (n=3) | — | — | — |
| 10 outside templates | 30 | 2 | 0.933 (n=15) | 0.000 (n=14) | — | — | — | — | — | — | 0.767 (n=30) | 0.700 (n=30) | — |

Category 10 outcomes (D): abstain=2, correct=21, wrong=7; answers using an unverified_path claim: 0

Category 7 by phrasing template (D): t0: action_cited=1.000 (n=10), entity=1.000 (n=10); t1: action_cited=1.000 (n=11), entity=1.000 (n=11); t2: action_cited=1.000 (n=9), entity=1.000 (n=9)

## Setup scripts (scratch graphs, torn down)

- seed 1 `eval_scratch_1_f996c5f3a9`: 6 steps, 10 questions, 3114.8 s
- seed 1 `eval_scratch_1_9ebf485ae0`: 24 steps, 10 questions, 10.6 s
- seed 1 `eval_scratch_1_97d170e155`: 0 steps, 10 questions, 9.0 s
- seed 2 `eval_scratch_2_e096d2892e`: 6 steps, 10 questions, 2427.4 s
- seed 2 `eval_scratch_2_570bb7bcd5`: 40 steps, 10 questions, 10.6 s
- seed 2 `eval_scratch_2_97d170e155`: 0 steps, 10 questions, 10.9 s
- seed 3 `eval_scratch_3_02bc3eb76c`: 6 steps, 10 questions, 9.2 s
- seed 3 `eval_scratch_3_58e4bab760`: 31 steps, 10 questions, 9.8 s
- seed 3 `eval_scratch_3_97d170e155`: 0 steps, 10 questions, 10.3 s
