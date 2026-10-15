import json
import sys

from brain import cli

from .conftest import PORTS


def test_probes_writes_one_document_keyed_by_version(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["brain", "probes", "--ports", ",".join(str(p) for p in PORTS.values())])
    cli.main()
    doc = json.loads((tmp_path / "evals/results/probes.json").read_text())
    assert set(doc) == set(PORTS)
    assert all(doc[v]["port"] == PORTS[v] and doc[v]["results"] for v in PORTS)
    assert json.loads(capsys.readouterr().out) == doc
