from ingest.extract import _canon_predicate, _cue_ok, AliasIndex, pattern_extract

T = {"team:infra": "Team", "team:payments": "Team", "system:ledger": "System", "person:ana": "Person"}


def test_cue_guard_blocks_over_inference():
    assert not _cue_ok("OWNS", "Infra runs backups and failover drills for the Ledger schema.")
    assert _cue_ok("OWNS", "Platform handed Ledger to Payments on 2026-04-01.")
    assert _cue_ok("OWNS", "Payments is responsible for Ledger.")
    assert not _cue_ok("DEPENDS_ON", "Ledger and Checkout were both discussed.")
    assert _cue_ok("DEPENDS_ON", "Checkout calls Ledger on every order.")
    assert _cue_ok("HAS_STATUS", "anything")          # literals are not guarded


def test_canon_predicate_maps_free_text():
    assert _canon_predicate("took over", "team:payments", "system:ledger", T) == ("OWNS", "")
    assert _canon_predicate("moved to", "person:ana", "team:payments", T) == ("MEMBER_OF", "primary")
    assert _canon_predicate("likes", "person:ana", "team:infra", T) is None
    assert _canon_predicate("owns", "system:ledger", "team:payments", T) is None   # wrong direction


def test_pattern_extractor_negation_and_hedge():
    idx = AliasIndex([{"id": "team:infra", "name": "Infra", "aliases": []}, {"id": "system:ledger", "name": "Ledger", "aliases": []}])
    t = "I think Infra owns Ledger?"
    xs = pattern_extract(t, idx.find(t), T)
    assert xs and xs[0].hedged


def test_llm_extract_applies_cue_guard(monkeypatch):
    """The guard must run on the real LLM path, not only in isolation (regression: tuple passed as predicate)."""
    from ingest import extract as ex
    monkeypatch.setattr(ex.providers, "complete", lambda *a, **k: {"json": {"facts": [
        {"predicate": "OWNS", "subject_ref": "team:infra", "object_ref": "system:ledger",
         "quote": "Infra runs backups and failover drills for the Ledger schema."}]}, "content": "", "tool_calls": []})
    idx = AliasIndex([{"id": "team:infra", "name": "Infra", "aliases": []}, {"id": "system:ledger", "name": "Ledger", "aliases": []}])
    t = "Infra runs backups and failover drills for the Ledger schema."
    assert ex.llm_extract(t, "", idx.find(t), T, {"team:infra": "Infra", "system:ledger": "Ledger"}) == []
