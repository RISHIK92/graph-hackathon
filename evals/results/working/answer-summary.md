# Answer layer

Fixed sample of up to 5 questions per category per seed; seeds [1].

| Metric | D (graph agent) |
|---|---|
| entity_match | 0.833 (n=12) |
| entity_f1 | 0.417 (n=6) |
| citation_precision | 0.771 (n=8) |
| citation_recall | 0.600 (n=10) |
| v2_pass | 1.000 (n=10) |
| v3_pass | 1.000 (n=10) |
| action_cited | 0.833 (n=6) |
| action_in_pack | 1.000 (n=6) |
| aggregate_acceptable | 0.600 (n=5) |
| aggregate_correct | 0.000 (n=5) |
| abstention P/R (D) | 0.00 / 0.00 |
| plan_ms p50/p95 (D) | 14 / 5152 |
| tools_ms p50/p95 (D) | 882 / 2406 |
| draft_ms p50/p95 (D) | 0 / 0 |
| verify_ms p50/p95 (D) | 0 / 0 |
| latency_ms p50/p95 (D) | 1019 / 6177 |
| draft citations, final (D) | 0 (must be 0) |

## Per category, variant D

| Category | n | abstained | entity_match | entity_f1 | citation_recall | dispute_disclosure | stale_error | proposal_labelling | action_cited | action_in_pack | aggregate_acceptable | aggregate_correct | history_judge |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 7 past belief | 5 | 0 | 1.000 (n=5) | 0.500 (n=5) | 0.600 (n=5) | — | — | — | 1.000 (n=5) | 1.000 (n=5) | — | — | — |
| 9 session memory | 5 | 2 | 0.600 (n=5) | — | 0.600 (n=5) | — | — | — | 0.000 (n=1) | 1.000 (n=1) | — | — | — |
| 10 outside templates | 5 | 3 | 1.000 (n=2) | 0.000 (n=1) | — | — | — | — | — | — | 0.600 (n=5) | 0.000 (n=5) | — |

Category 10 outcomes (D): abstain=3, wrong=2; answers using an unverified_path claim: 0

Category 7 by phrasing template (D): t0: action_cited=1.000 (n=4), entity=1.000 (n=4); t2: action_cited=1.000 (n=1), entity=1.000 (n=1)

## Setup scripts (scratch graphs, torn down)

- seed 1 `eval_scratch_1_9ebf485ae0`: 24 steps, 5 questions, 8.3 s
- seed 1 `eval_scratch_1_97d170e155`: 0 steps, 5 questions, 8.6 s
