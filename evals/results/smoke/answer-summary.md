# Answer layer

Fixed sample of up to 3 questions per category per seed; seeds [1].

| Metric | D (graph agent) |
|---|---|
| entity_match | 0.444 (n=9) |
| entity_f1 | 0.250 (n=2) |
| citation_precision | 0.333 (n=4) |
| citation_recall | 0.167 (n=6) |
| v2_pass | 1.000 (n=8) |
| v3_pass | 1.000 (n=8) |
| proposal_labelling | 0.333 (n=3) |
| proposal_as_current | 0.000 (n=3) |
| action_cited | 0.167 (n=6) |
| action_in_pack | 0.167 (n=6) |
| aggregate_acceptable | 0.667 (n=3) |
| aggregate_correct | 0.000 (n=3) |
| abstention P/R (D) | 0.00 / 0.00 |
| plan_ms p50/p95 (D) | 2317 / 4242 |
| tools_ms p50/p95 (D) | 3833 / 10449 |
| draft_ms p50/p95 (D) | 2 / 20 |
| verify_ms p50/p95 (D) | 1 / 11 |
| latency_ms p50/p95 (D) | 6128 / 14360 |
| draft citations, final (D) | 0 (must be 0) |

## Per category, variant D

| Category | n | abstained | entity_match | entity_f1 | citation_recall | dispute_disclosure | stale_error | proposal_labelling | action_cited | action_in_pack | aggregate_acceptable | aggregate_correct | history_judge |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 4-pending pending draft | 3 | 0 | 1.000 (n=3) | 0.000 (n=1) | — | — | — | 0.333 (n=3) | 0.333 (n=3) | 0.333 (n=3) | — | — | — |
| 7 past belief | 3 | 0 | 0.333 (n=3) | 0.500 (n=1) | 0.333 (n=3) | — | — | — | 0.000 (n=3) | 0.000 (n=3) | — | — | — |
| 9 session memory | 3 | 2 | 0.000 (n=3) | — | 0.000 (n=3) | — | — | — | — | — | — | — | — |
| 10 outside templates | 3 | 2 | — | — | — | — | — | — | — | — | 0.667 (n=3) | 0.000 (n=3) | — |

Category 10 outcomes (D): abstain=2, wrong=1; answers using an unverified_path claim: 0

Category 7 by phrasing template (D): t0: action_cited=0.000 (n=1), entity=0.500 (n=1); t1: action_cited=0.000 (n=2), entity=0.250 (n=2)

## Setup scripts (scratch graphs, torn down)

- seed 1 `eval_scratch_1_f996c5f3a9`: 6 steps, 3 questions, 139.9 s
- seed 1 `eval_scratch_1_9ebf485ae0`: 24 steps, 3 questions, 88.2 s
- seed 1 `eval_scratch_1_97d170e155`: 0 steps, 3 questions, 114.9 s
