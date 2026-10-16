# Invalid as a laguna measurement

This run (commit 3a6eee1) was meant to measure `poolside/laguna-xs-2.1` as planner and drafter. Every laguna
call failed: legacy `LLM_MODEL` received DeepSeek-only request settings (reasoning off and
`provider.require_parameters`), and failed calls fall back to the rule-based planner and the graph's
deterministic draft. So the numbers here measure the deterministic path, not laguna. The cause was fixed in
8314b00. The files are kept as they were; the item 20 "before" is the A1 arm of the re-run A/B instead.
