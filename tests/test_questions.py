"""Eval gold (06 §6, item 20): copied from the declarations, never computed by a chain function."""
from evals import questions
from evals.gold import SpanGold, World
from brain.config import ROOT


def test_ownership_gold_includes_the_owner_teams_lead(monkeypatch):
    """The ownership answer is "T owns X. P leads T." (M4), so the lead's declaration is gold evidence too:
    one group for the owner, one for the owner team's lead at the same date."""
    monkeypatch.setattr(SpanGold, "spans", lambda self, ref, latest_only=False, states=None: [ref])
    world = World.load(ROOT / "world" / "seeds" / "1")
    gen = questions.Generator(world, None, 1)
    own = [q for q in gen.build() if q["category"] == 3 and q["expected_relation_types"] == ["OWNS"]]
    assert own
    for q in own:
        team = q["expected_fact"]["subject_id"]
        lead = gen.cg.state(("LEADS", "", team), world.today) if team.startswith("team:") else None
        assert len(q["gold_evidence_groups"]) == (2 if lead else 1), q["question"]
        if lead:
            assert q["gold_evidence_groups"][1] == gen.group(("LEADS", "", team), lead["value"])
