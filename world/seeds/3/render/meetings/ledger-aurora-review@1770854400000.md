# Ledger Aurora review

Date: 2026-02-12
Attendees: person:priya-raman, person:ana-costa, person:marta-kowalczyk, person:bob-lindqvist

We reviewed the plan to move Ledger from Postgres Main to Aurora. ADR-007 was accepted because Postgres Main could not sustain Ledger write volume during month-end close.

Ana Costa works on Core Banking. Bob Lindqvist will keep Postgres Main snapshots for 90 days after the cutover.
