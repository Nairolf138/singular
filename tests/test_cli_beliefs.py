from __future__ import annotations

import json

import singular.cli as cli
from singular.beliefs.store import BeliefStore


def test_cli_beliefs_audit_and_reset(tmp_path, capsys) -> None:
    life_dir = tmp_path / "life"
    store = BeliefStore(path=life_dir / "mem" / "beliefs.json")
    store.update_after_run("operator:demo", success=True, evidence="accepted")

    assert cli.main(["--home", str(life_dir), "beliefs", "audit"]) == 0
    out = capsys.readouterr().out
    assert "operator:demo" in out

    assert (
        cli.main(
            [
                "--home",
                str(life_dir),
                "--format",
                "json",
                "beliefs",
                "reset",
                "--hypothesis",
                "operator:demo",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "supprimées" in out

    payload = json.loads((life_dir / "mem" / "beliefs.json").read_text(encoding="utf-8"))
    assert payload == {}
