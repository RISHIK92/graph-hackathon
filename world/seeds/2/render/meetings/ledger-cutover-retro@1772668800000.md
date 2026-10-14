# Ledger cutover retro

Date: 2026-03-05
Attendees: person:ana-costa, person:priya-raman, person:bob-lindqvist, person:ines-duarte

On 2026-03-02, we dropped the dependency on Postgres Main from Ledger. Ledger depends on Aurora.

Ines Duarte confirmed that replica lag stayed under one second during the cutover.
