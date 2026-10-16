# Stopped after 20 answers

The first full live run (code 7e45e0e) aborted itself: the guard counted fixed-shape answers the drafter skips
as fallbacks, and laguna's multi-hop drafts overran the 10 s limit. The action eval failed learn_fact_dedup_undo
(laguna's quote left out a name). All three fixed in ce4ed34; the full run was repeated there. Files kept.
