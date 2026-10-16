# ABORTED after 30 answers: drafter error rate 3/29

Resume with the same command and cache.

# Answer layer

Fixed sample of up to 10 questions per category per seed; seeds [1, 2, 3].

| Metric | D (graph agent) |
|---|---|
| entity_match | 1.000 (n=30) |
| entity_f1 | 0.560 (n=30) |
| citation_precision | 0.780 (n=30) |
| citation_recall | 0.975 (n=30) |
| v2_pass | 0.963 (n=30) |
| v3_pass | 0.990 (n=30) |
| abstention P/R (D) | 0.00 / 0.00 |
| plan_ms p50/p95 (D) | 0 / 3064 |
| tools_ms p50/p95 (D) | 47 / 95 |
| draft_ms p50/p95 (D) | 3642 / 8197 |
| verify_ms p50/p95 (D) | 569 / 7154 |
| latency_ms p50/p95 (D) | 5402 / 16508 |
| draft citations, final (D) | 0 (must be 0) |

## Per category, variant D

| Category | n | abstained | entity_match | entity_f1 | citation_recall | dispute_disclosure | stale_error | proposal_labelling | action_cited | action_in_pack | aggregate_acceptable | aggregate_correct | history_judge |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 single-hop | 10 | 0 | 1.000 (n=10) | 0.600 (n=10) | 1.000 (n=10) | — | — | — | — | — | — | — | — |
| 2 multi-hop | 10 | 0 | 1.000 (n=10) | 0.550 (n=10) | 0.925 (n=10) | — | — | — | — | — | — | — | — |
| 3 ownership | 10 | 0 | 1.000 (n=10) | 0.530 (n=10) | 1.000 (n=10) | — | — | — | — | — | — | — | — |

## Run report

| Rate | Value |
|---|---|
| deterministic fallback | 1 of 30 answers the drafter should have written |
| escalation | 2 of 30 |
| checker blocked | 2 of 30 |

Served: checker: typesafe/jev-1.14 via TypeSafe (32); drafter: anthropic/claude-haiku-5.5 via Azure (1); drafter: poolside/laguna-xs-2.1 via Poolside (23); escalation: anthropic/claude-haiku-5.5 via Azure (2); planner: poolside/laguna-xs-2.1 via Poolside (9)
