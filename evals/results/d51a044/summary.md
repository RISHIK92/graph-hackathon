# Eval summary (d51a044, seeds [1, 2, 3])

Retrieval layer, mean over seeds. Gold comes from the world declarations only. Scripted categories
(4-pending, 7, 9) run only in the answer layer (`answer-summary.md`); 10 has no span gold.

## recall@5

| Category | A | A+R | B | C | D | E |
|---|---|---|---|---|---|---|
| 1 single-hop | 0.673 | 0.953 | 0.653 | 1.000 | 1.000 | 1.000 |
| 2 multi-hop | 0.120 | 0.167 | 0.018 | 0.965 | 1.000 | 1.000 |
| 3 ownership | 0.327 | 0.607 | 0.333 | 1.000 | 1.000 | 1.000 |
| 4 decision trace | 0.480 | 0.480 | 0.347 | 0.920 | 1.000 | 1.000 |
| 5 stale fact | 0.667 | 0.698 | 0.344 | 1.000 | 1.000 | 1.000 |
| 8 disputed | 0.546 | 0.687 | 0.328 | 0.526 | 1.000 | 1.000 |

## recall@10

| Category | A | A+R | B | C | D | E |
|---|---|---|---|---|---|---|
| 1 single-hop | 0.773 | 0.960 | 0.853 | 1.000 | 1.000 | 1.000 |
| 2 multi-hop | 0.183 | 0.237 | 0.056 | 1.000 | 1.000 | 1.000 |
| 3 ownership | 0.487 | 0.807 | 0.487 | 1.000 | 1.000 | 1.000 |
| 4 decision trace | 0.480 | 0.480 | 0.440 | 0.960 | 1.000 | 1.000 |
| 5 stale fact | 0.750 | 0.812 | 0.656 | 1.000 | 1.000 | 1.000 |
| 8 disputed | 0.624 | 0.749 | 0.453 | 0.588 | 1.000 | 1.000 |

## mrr

| Category | A | A+R | B | C | D | E |
|---|---|---|---|---|---|---|
| 1 single-hop | 0.521 | 0.808 | 0.419 | 0.937 | 1.000 | 1.000 |
| 2 multi-hop | 0.147 | 0.210 | 0.061 | 0.755 | 1.000 | 1.000 |
| 3 ownership | 0.272 | 0.408 | 0.222 | 0.837 | 1.000 | 1.000 |
| 4 decision trace | 0.390 | 0.393 | 0.191 | 0.847 | 0.900 | 0.900 |
| 5 stale fact | 0.455 | 0.472 | 0.180 | 0.540 | 1.000 | 1.000 |
| 8 disputed | 0.721 | 0.879 | 0.423 | 0.764 | 1.000 | 1.000 |

## fact_accuracy

| Category | A | A+R | B | C | D | E |
|---|---|---|---|---|---|---|
| 1 single-hop | 0.000 | 0.000 | 0.000 | 0.700 | 1.000 | 1.000 |
| 3 ownership | 0.000 | 0.000 | 0.000 | 0.693 | 1.000 | 1.000 |
| 5 stale fact | 0.000 | 0.000 | 0.000 | 0.125 | 1.000 | 1.000 |
| 8 disputed | 0.000 | 0.000 | 0.000 | 0.558 | 1.000 | 1.000 |

## stale_leak

| Category | A | A+R | B | C | D | E |
|---|---|---|---|---|---|---|
| 5 stale fact | 0.855 | 0.926 | 0.411 | 1.000 | 0.000 | 0.000 |

## dispute_surfacing

| Category | A | A+R | B | C | D | E |
|---|---|---|---|---|---|---|
| 8 disputed | 0.415 | 0.540 | 0.177 | 0.000 | 1.000 | 1.000 |

## path_coverage

| Category | A | A+R | B | C | D | E |
|---|---|---|---|---|---|---|
| 1 single-hop | 0.000 | 0.000 | 0.000 | 0.980 | 1.000 | 1.000 |
| 2 multi-hop | 0.000 | 0.000 | 0.000 | 0.981 | 0.981 | 0.981 |
| 3 ownership | 0.000 | 0.000 | 0.000 | 1.000 | 1.000 | 1.000 |
| 4 decision trace | 0.000 | 0.000 | 0.000 | 0.633 | 0.800 | 0.800 |
| 5 stale fact | 0.000 | 0.000 | 0.000 | 1.000 | 1.000 | 1.000 |
| 8 disputed | 0.000 | 0.000 | 0.000 | 1.000 | 1.000 | 1.000 |
| 10 outside templates | 0.000 | 0.000 | 0.000 | 0.947 | 0.980 | 0.980 |

## Recall@5 without anchor questions

| Category | A | A+R | B | C | D | E |
|---|---|---|---|---|---|---|
| 1 single-hop | 0.684 | 0.964 | 0.641 | 1.000 | 1.000 | 1.000 |
| 2 multi-hop | 0.176 | 0.227 | 0.035 | 0.933 | 1.000 | 1.000 |
| 3 ownership | 0.265 | 0.579 | 0.307 | 1.000 | 1.000 | 1.000 |
| 4 decision trace | 0.500 | 0.500 | 0.317 | 0.900 | 1.000 | 1.000 |
| 4-pending pending draft | — | — | — | — | — | — |
| 5 stale fact | 0.681 | 0.722 | 0.347 | 1.000 | 1.000 | 1.000 |
| 6 unanswerable | — | — | — | — | — | — |
| 7 past belief | — | — | — | — | — | — |
| 8 disputed | 0.558 | 0.660 | 0.328 | 0.523 | 1.000 | 1.000 |
| 9 session memory | — | — | — | — | — | — |
| 10 outside templates | — | — | — | — | — | — |

## Rule-3 gate (C and D vs best of A, A+R; Recall@5; margin must exceed seed noise)

| Category | Variant | R@5 | Best baseline | Margin | Noise | Pass |
|---|---|---|---|---|---|---|
| multi-hop | C | 0.965 | 0.167 | 0.798 | 0.041 | yes |
| multi-hop | D | 1.0 | 0.167 | 0.833 | 0.041 | yes |
| ownership | C | 1.0 | 0.607 | 0.393 | 0.104 | yes |
| ownership | D | 1.0 | 0.607 | 0.393 | 0.104 | yes |
| decision trace | C | 0.92 | 0.48 | 0.44 | 0.0 | yes |
| decision trace | D | 1.0 | 0.48 | 0.52 | 0.0 | yes |
| stale fact | C | 1.0 | 0.698 | 0.302 | 0.015 | yes |
| stale fact | D | 1.0 | 0.698 | 0.302 | 0.015 | yes |
