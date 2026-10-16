# ABORTED after 20 answers: 5 of 15 answers fell back to the deterministic draft

Resume with the same command and cache.

# Answer layer

Fixed sample of up to 10 questions per category per seed; seeds [1, 2, 3].

| Metric | D (graph agent) |
|---|---|
| entity_match | 1.000 (n=20) |
| entity_f1 | 0.583 (n=20) |
| citation_precision | 0.871 (n=20) |
| citation_recall | 1.000 (n=20) |
| v2_pass | 0.951 (n=20) |
| v3_pass | 1.000 (n=20) |
| abstention P/R (D) | 0.00 / 0.00 |
| plan_ms p50/p95 (D) | 1 / 5669 |
| tools_ms p50/p95 (D) | 68 / 283 |
| draft_ms p50/p95 (D) | 3810 / 12539 |
| verify_ms p50/p95 (D) | 633 / 7221 |
| latency_ms p50/p95 (D) | 8815 / 13374 |
| draft citations, final (D) | 0 (must be 0) |

## Per category, variant D

| Category | n | abstained | entity_match | entity_f1 | citation_recall | dispute_disclosure | stale_error | proposal_labelling | action_cited | action_in_pack | aggregate_acceptable | aggregate_correct | history_judge |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 single-hop | 10 | 0 | 1.000 (n=10) | 0.600 (n=10) | 1.000 (n=10) | — | — | — | — | — | — | — | — |
| 2 multi-hop | 10 | 0 | 1.000 (n=10) | 0.567 (n=10) | 1.000 (n=10) | — | — | — | — | — | — | — | — |

## Run report

| Rate | Value |
|---|---|
| deterministic fallback | 7 of 20 answers the drafter should have written |
| escalation | 1 of 20 |
| checker blocked | 2 of 20 |

Served: checker: typesafe/jev-1.14 via TypeSafe (21); drafter: poolside/laguna-xs-2.1 via Poolside (11); escalation: anthropic/claude-haiku-5.5 via Azure (1); planner: poolside/laguna-xs-2.1 via Poolside (8)
