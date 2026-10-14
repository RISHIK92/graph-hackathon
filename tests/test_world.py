"""Phase 2: synthetic world model, demo anchor and renderer (05 §3, render contract)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from world import checks, paraphrase
from world.build import dump_json, dump_yaml, write_seed
from world.common import GenerationError, word_re
from world.generator import build_seed, load_anchor

ROOT = Path(__file__).resolve().parent.parent
SEEDS = (1, 2, 3)


@pytest.fixture(scope="module")
def built():
    return {s: build_seed(s) for s in SEEDS}


# determinism

def test_same_seed_same_bytes_in_process(built):
    world, files, manifest = build_seed(1)
    w0, f0, m0 = built[1]
    assert dump_yaml(world) == dump_yaml(w0)
    assert dump_json(manifest) == dump_json(m0)
    assert files == f0


def test_same_seed_same_bytes_across_processes(tmp_path):
    outs = []
    for hashseed in ("0", "4242"):
        out = tmp_path / hashseed
        env = dict(os.environ, PYTHONHASHSEED=hashseed)
        env.pop("OPENROUTER_API_KEY", None)
        subprocess.run([sys.executable, "-m", "world.build", "--seeds", "2", "--out", str(out), "--quiet"],
                       cwd=ROOT, env=env, check=True)
        outs.append({p.relative_to(out): p.read_bytes() for p in sorted(out.rglob("*")) if p.is_file()})
    assert outs[0] == outs[1]
    assert len(outs[0]) > 100


def test_different_seeds_differ(built):
    assert dump_yaml(built[1][0]) != dump_yaml(built[2][0])


@pytest.mark.parametrize("seed", SEEDS)
def test_committed_render_matches_generator(seed, built, tmp_path):
    committed = ROOT / "world" / "seeds" / str(seed)
    if not committed.exists():
        pytest.skip("renders not built yet")
    write_seed(seed, tmp_path)
    fresh = {p.relative_to(tmp_path / str(seed)): p.read_bytes() for p in (tmp_path / str(seed)).rglob("*") if p.is_file()}
    old = {p.relative_to(committed): p.read_bytes() for p in committed.rglob("*") if p.is_file()}
    assert fresh == old, "world/seeds is stale: rerun `python -m world.build --seeds 1 2 3`"


# checks

@pytest.mark.parametrize("seed", SEEDS)
def test_every_check_passes(seed, built):
    world, files, manifest = built[seed]
    from world.generator import Generator  # noqa: F401  (build_seed already ran run_all)
    assert world["changes"] and manifest["documents"]
    assert world["D_reorg"] == world["D_transfer"]
    cells = checks.check_balance(world["changes"])
    assert len(set(cells.values())) == 1
    counts = checks.check_distractors(world, manifest)
    for t in checks.DISTRACTOR_TYPES:
        assert counts[t] > 0, t


@pytest.mark.parametrize("seed", SEEDS)
def test_target_sizes(seed, built):
    world, files, manifest = built[seed]
    assert len(world["people"]) == 40 and len(world["teams"]) == 6
    assert len(world["projects"]) == 10 and len(world["systems"]) == 15
    assert len(world["decisions"]) == 12 and len(world["tickets"]) == 60
    assert sum(1 for d in manifest["documents"] if d["kind"] == "chat") == 400
    preds = {c["predicate"] + c["qualifier"] for c in world["changes"]}
    assert {"OWNS", "LEADS", "MEMBER_OFprimary", "DEPENDS_ON"} <= preds


def _mutated(seed, fn):
    with pytest.raises(GenerationError) as e:
        build_seed(seed, mutate=fn)
    return str(e.value)


def _change(changes, cid):
    return next(c for c in changes if c["change_id"] == cid)


def test_broken_declaration_fails_rank_rule():
    def flip(changes):
        _change(changes, "anchor_ledger_transfer")["expected_outcome"] = "disputed"
        _change(changes, "anchor_ledger_transfer")["challenger_correct"] = True
    assert "rank rule" in _mutated(1, flip)

    def flip_disputed(changes):
        c = _change(changes, "anchor_wrong_challenger")
        c["expected_outcome"], c["challenger_correct"], c["stale_docs"] = "resolved", None, []
    assert "rank rule" in _mutated(1, flip_disputed)


def test_broken_stale_docs_fails():
    def drop(changes):
        _change(changes, "anchor_ledger_transfer")["stale_docs"] = []
    assert "stale_docs" in _mutated(1, drop)


def test_broken_equal_date_tag_fails():
    def untag(changes):
        c = next(c for c in changes if "equal_date_dispute" in c["tags"])
        c["tags"].remove("equal_date_dispute")
    assert "equal" in _mutated(1, untag)


def test_broken_balance_fails():
    def tip(changes):
        c = next(c for c in changes if c["expected_outcome"] == "disputed" and c["challenger_correct"]
                 and "anchor" not in c["tags"])
        c["challenger_correct"] = c["true"] = False
    assert "balance" in _mutated(1, tip)


def test_untagged_gap_fails():
    def untag(changes):
        c = next(c for c in changes if "fallback_gap" in c["tags"])
        c["tags"].remove("fallback_gap")
    assert "fallback_gap" in _mutated(1, untag)


def test_public_figure_name_fails():
    anchor = load_anchor()
    anchor["people"][1]["name"] = "Elon Musk"
    with pytest.raises(GenerationError, match="public figure"):
        build_seed(1, anchor=anchor)


def test_anchor_guarantee_breaks_fail():
    anchor = load_anchor()
    chat = next(d for d in anchor["docs"] if d["kind"] == "chat" and d.get("thread"))
    chat["sentences"] = [{"text": "Infra owns Ledger now.", "claims": [{"p": "OWNS", "s": "team:infra", "o": "system:ledger"}]}]
    with pytest.raises(GenerationError):
        build_seed(1, anchor=anchor)
    anchor = load_anchor()
    rds42 = next(t for t in anchor["tickets"] if t["key"] == "RDS-42")
    rds42["assignee_timeline"] = [{"who": "person:priya-raman", "at": "2026-09-21"}]
    with pytest.raises(GenerationError, match="G9"):
        build_seed(1, anchor=anchor)


# manifest offsets

def _entities_of(ref: str, states: str, facts: dict, changes: dict) -> tuple[list[str], list[str]]:
    """(entity IDs, literal values) a sentence ref is about: the key plus the side it states."""
    kind, rid = ref.split(":", 1)
    if kind == "fact":
        f = facts[rid]
        ents = [f["subject"]] + ([f["object"]] if f["object"] else [])
        return ents, [f["value"]] if f["value"] else []
    c = changes[rid]
    ents, lits = [], []
    for x in [c["key"], c[states]]:
        for y in x.split(">"):
            if ":" in y:
                ents.append(y)
            elif y not in ("", "+", "-"):
                lits.append(y)
    return ents, lits


@pytest.mark.parametrize("seed", SEEDS)
def test_manifest_offsets_slice_to_named_entities(seed, built):
    world, files, manifest = built[seed]
    names: dict[str, list[str]] = {}
    for e in world["people"] + world["teams"] + world["projects"] + world["systems"]:
        names[e["id"]] = [e["name"]] + e["aliases"]
    for d in world["decisions"]:
        names[d["id"]] = [d["number"]]
    for t in world["tickets"]:
        names[t["id"]] = [t["key"]]
    facts = {f["fact_id"]: f for f in world["facts"]}
    changes = {c["change_id"]: c for c in world["changes"]}
    chat_cache: dict[str, list[str]] = {}
    n = 0
    for d in manifest["documents"]:
        if d["kind"] == "chat":
            path, idx = d["path"].split("#")
            lines = chat_cache.setdefault(path, files[path].rstrip("\n").split("\n"))
            content = json.loads(lines[int(idx)])["text"]
        else:
            content = files[d["path"]]
        for s in d["sentences"]:
            sl = content[s["char_start"]:s["char_end"]]
            assert sl == s["text"] and sl.strip(), (d["path"], s)
            n += 1
            if s["states"] == "rationale":
                assert d["kind"] == "adr"
                continue
            ents, lits = _entities_of(s["ref"], s["states"], facts, changes)
            for eid in ents:
                if d["kind"] == "roster" and eid.startswith("team:"):
                    continue  # the team is the table's heading
                if d["kind"] == "ticket" and eid.startswith("ticket:"):
                    continue  # the ticket is the file itself
                if d["kind"] == "ticket" and s["ref"].startswith("change:") and changes[s["ref"][7:]]["predicate"] == "ABOUT" \
                        and s["states"] == "to":
                    continue  # the replacement row closes the old component implicitly (A65)
                if d["kind"] == "ticket" and s["ref"].startswith("fact:") and facts[s["ref"][5:]]["negated"]:
                    continue
                ok = eid in sl or any(word_re(x).search(sl) for x in names[eid])
                assert ok, f"{d['path']}: {sl!r} does not name {eid}"
            for lit in lits:
                assert lit in sl, f"{d['path']}: {sl!r} does not state {lit}"
    assert n > 1000


@pytest.mark.parametrize("seed", SEEDS)
def test_manifest_shape(seed, built):
    world, files, manifest = built[seed]
    assert manifest["seed"] == seed and manifest["D_transfer"] == world["D_transfer"]
    for d in manifest["documents"]:
        assert d["doc_key"] == f"{d['kind']}:{d['system']}:{d['external_id']}"
        assert d["path"].split("#")[0] in files
        assert d["phase"] == (1 if d["kind"] in ("roster", "catalog", "adr", "ticket") else 2)
        assert d["created_at"] <= d["updated_at"] <= world["company"]["today"]
        if d["kind"] != "chat":
            assert d["path"].endswith(f"@{d['updated_at']}" + Path(d["path"]).suffix)
    for path, text in files.items():
        if path.endswith(".yaml"):
            yaml.safe_load(text)
        elif path.endswith(".json"):
            json.loads(text)
        elif path.endswith(".jsonl"):
            for line in text.splitlines():
                m = json.loads(line)
                assert list(m)[:4] == ["channel", "ts", "author", "text"]


# demo anchor

@pytest.mark.parametrize("seed", SEEDS)
def test_anchor_guarantees(seed, built):
    world, files, manifest = built[seed]
    A = world["anchor"]
    ents = {e["id"]: e for e in world["people"] + world["teams"] + world["projects"] + world["systems"]}
    # G1/G5 names
    assert ents["system:ledger"]["name"] == "Ledger" and "ledger-service" in ents["system:ledger"]["aliases"]
    assert ents["team:infra"]["name"] == "Infra" and "Infrastructure" in ents["team:infra"]["aliases"]
    # G2/G3
    c = next(x for x in world["changes"] if x["change_id"] == A["ledger_transfer_change"])
    assert (c["from"], c["to"], c["at"], c["expected_outcome"]) == ("team:platform", "team:payments",
                                                                    world["D_transfer"], "resolved")
    assert c["stale_docs"] == ["wiki:confluence:ledger-overview"]
    wiki = [d for d in manifest["documents"] if d["doc_key"] == "wiki:confluence:ledger-overview"]
    assert len(wiki) == 1 and wiki[0]["updated_at"] < world["D_transfer"]
    # G4: no source says Infra owns Ledger
    for d in manifest["documents"]:
        for s in d["sentences"]:
            assert not ("Infra" in s["text"] and "owns Ledger" in s["text"])
    # G9
    rds = json.loads(next(v for k, v in files.items() if k.startswith("tickets/RDS-42@")))
    assert rds["assignee_history"] == [] and [x["state"] for x in rds["state_history"]] == ["open"]
    assert [x["about"] for x in rds["component_history"]] == ["system:ledger"]
    # G7 ADR ids
    nums = {d["id"]: d for d in world["decisions"]}
    assert nums[A["adr_new"]]["replaces"] == [A["adr_old"]]
    assert nums[A["adr_old"]]["status_timeline"][-1]["status"] == "superseded"
    # G11
    w = next(x for x in world["changes"] if x["change_id"] == "anchor_wrong_challenger")
    assert w["challenger_correct"] is False and "chat_contradiction" in w["tags"]
    # G12
    assert world["demo_identity"] == "person:jonah-feld"
    assert not any(f["predicate"] == "LEADS" and f["subject"] == world["demo_identity"] for f in world["facts"])


def test_paraphrase_is_noop_without_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert paraphrase.paraphrase("Platform owns Ledger.", ["Platform", "Ledger"], 1, requested=True) == "Platform owns Ledger."
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    assert paraphrase.paraphrase("Platform owns Ledger.", ["Platform", "Ledger"], 1, requested=False) == "Platform owns Ledger."
