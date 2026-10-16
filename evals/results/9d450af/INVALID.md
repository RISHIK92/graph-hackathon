# Arm A is invalid; no winner

Arm A (`ab-A`, `ab-A-warm`) made no successful laguna call: its cold cache holds judge calls only, because legacy
`LLM_MODEL` received DeepSeek-only request settings (fixed in 8314b00). All 29 A answers are the graph's
deterministic draft. Arm B is a real measurement of DeepSeek + the Jev checker, but before the bounded planner and
drafter calls of 45ff526. The A/B is re-run on the fixed code; these files are kept as they were.
