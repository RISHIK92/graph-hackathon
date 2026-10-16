# Superseded

A1 and A2 of the re-run A/B on 88ebbd4. A2 tripped the stop rule (1 drafter fallback, 2 checker blocks), so B
never ran, and both arms show one ~170 s answer from a bounded call whose deadline didn't fire (fixed in 6ea1716).
All three arms were re-run on 85503af. Files kept as they were.
