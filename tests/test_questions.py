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


def test_judged_categories_carry_a_reference_answer_from_declarations(monkeypatch):
    """Item 20 step 0: the judge scores against a reference answer written from the declarations (never from
    model output) for categories 5, 7 and 8; it names the expected entities."""
    monkeypatch.setattr(SpanGold, "spans", lambda self, ref, latest_only=False, states=None: [ref])
    world = World.load(ROOT / "world" / "seeds" / "1")
    gen = questions.Generator(world, None, 1)
    names = world.names()
    judged = [q for q in gen.build() if q["category"] in (5, 7, 8)]
    assert {q["category"] for q in judged} == {5, 7, 8}
    for q in judged:
        ref = q.get("reference_answer") or ""
        assert all(names[e] in ref for e in q["expected_entities"]), (q["question"], ref)


def test_graph_algorithm_category_has_about_ten_questions_per_seed(monkeypatch):
    """Gate C14: category 11 grows from 3 to about 10 per seed, gold from the declarations (dependents counted
    from DEPENDS_ON facts, leads from LEADS, ownership from OWNS), never from the algorithms."""
    monkeypatch.setattr(SpanGold, "spans", lambda self, ref, latest_only=False, states=None: [ref])
    for seed in ("1", "2", "3"):
        world = World.load(ROOT / "world" / "seeds" / seed)
        algo = [q for q in questions.Generator(world, None, int(seed)).build() if q["category"] == 11]
        assert 8 <= len(algo) <= 12, (seed, len(algo))
        assert len({q["question"] for q in algo}) == len(algo)
        assert all(q["expected_entities"] for q in algo)
