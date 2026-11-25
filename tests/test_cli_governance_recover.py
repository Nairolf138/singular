from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import singular.cli as cli
from singular.governance.policy import (
    circuit_state_path,
    load_circuit_state,
    save_circuit_state,
)
from singular.life.sandbox_scoring import SandboxScore


def test_recovery_requires_cooldown_or_audited_emergency(
    tmp_path, monkeypatch, local_sandbox, capsys
) -> None:
    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))
    state = load_circuit_state(tmp_path)
    state.update(
        state="open",
        initial_cause={"category": "timeout"},
        cooldown_deadline=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    )
    save_circuit_state(state, tmp_path)

    assert cli._diagnose_governance(output_format="json") == 1
    assert json.loads(capsys.readouterr().out)["recommended_action"].startswith(
        "Borner"
    )
    assert (
        cli._recover_governance(
            operator="flo", justification="cause corrigée", emergency=False
        )
        == 1
    )
    assert "cooldown non échu" in capsys.readouterr().err
    assert load_circuit_state(tmp_path)["state"] == "open"

    assert (
        cli._recover_governance(
            operator="flo", justification="sonde supervisée", emergency=True
        )
        == 0
    )
    recovered = load_circuit_state(tmp_path)
    assert recovered["state"] == "closed"
    assert recovered["last_probe"]["success"] is True
    assert recovered["closure_decision"]["operator"] == "flo"
    audit = circuit_state_path(tmp_path).parent / "governance_circuit_audit.jsonl"
    assert [json.loads(row)["new_state"] for row in audit.read_text().splitlines()] == [
        "half_open",
        "closed",
    ]
    assert (
        cli._recover_governance(
            operator="flo", justification="idempotence", emergency=False
        )
        == 0
    )


def test_failed_recovery_probe_keeps_circuit_open_and_records_failure(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))
    state = load_circuit_state(tmp_path)
    state["state"] = "open"
    save_circuit_state(state, tmp_path)
    monkeypatch.setattr(
        "singular.life.loop.score_code_with_error",
        lambda code: SandboxScore(
            score=float("-inf"),
            ok=False,
            error_type="invalid_candidate",
            error_message="probe rejected",
        ),
    )

    assert cli._diagnose_governance() == 1
    assert "Circuit gouvernance: open" in capsys.readouterr().out
    assert (
        cli._recover_governance(
            operator="flo", justification="vérification", emergency=False
        )
        == 1
    )
    assert "circuit open" in capsys.readouterr().out
    persisted = load_circuit_state(tmp_path)
    assert persisted["state"] == "open"
    assert persisted["last_probe"]["error_type"] == "invalid_candidate"
    assert persisted["closure_decision"] is None


def test_recovery_refuses_unsafe_skill_without_emergency(
    tmp_path, monkeypatch, local_sandbox, capsys
) -> None:
    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "invalid.py").write_text("raise RuntimeError('bad')\n", encoding="utf-8")
    state = load_circuit_state(tmp_path)
    state["state"] = "open"
    save_circuit_state(state, tmp_path)

    assert (
        cli._recover_governance(
            operator="flo", justification="vérification", emergency=False
        )
        == 1
    )
    assert "cause non corrigée" in capsys.readouterr().err
    assert load_circuit_state(tmp_path)["state"] == "open"


def test_malformed_cooldown_is_treated_as_active(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))
    state = load_circuit_state(tmp_path)
    state.update(state="open", cooldown_deadline="invalid date")
    save_circuit_state(state, tmp_path)

    assert (
        cli._recover_governance(
            operator="flo", justification="attendre une date valide", emergency=False
        )
        == 1
    )
    assert "cooldown non échu" in capsys.readouterr().err
    assert load_circuit_state(tmp_path)["state"] == "open"
