import json
from pathlib import Path

from singular.identity import IdentityCoherenceGuard, IdentityInvariants, detect_contradictions


def test_detect_contradictions_between_beliefs_goals_and_history() -> None:
    contradictions = detect_contradictions(
        beliefs=[{"hypothesis": "prefer safe mode"}],
        goals=[{"name": "not prefer safe mode"}],
        history=[{"summary": "prefer safe mode"}],
    )

    assert len(contradictions) == 1
    assert contradictions[0]["canonical"] == "prefer safe mode"


def test_guard_blocks_invariant_violation_and_audits_gap(tmp_path: Path) -> None:
    guard = IdentityCoherenceGuard(
        invariants=IdentityInvariants(
            life_name="Singular",
            cardinal_values=("integrity", "care"),
            long_term_commitments=("protect memory",),
        ),
        root=tmp_path,
    )

    decision = guard.evaluate_decision(
        decision={
            "life_name": "OtherName",
            "values": ["integrity"],
            "action": "not protect memory",
            "summary": "rename and purge long-term traces",
        },
        beliefs=[{"hypothesis": "protect memory"}],
        goals=[{"name": "not protect memory"}],
        history=[{"summary": "protect memory"}],
    )

    assert decision.accepted is False
    assert decision.status == "blocked"
    assert "life_name_mismatch" in decision.invariant_violations
    assert any("cardinal_values_missing" in item for item in decision.invariant_violations)
    assert any("long_term_commitment_negated" in item for item in decision.invariant_violations)

    audit_path = tmp_path / "mem" / "identity_coherence_audit.jsonl"
    entries = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert len(entries) == 1
    assert entries[0]["status"] == "blocked"
    assert entries[0]["accepted"] is False


def test_guard_recovers_after_drift_with_compliant_decision(tmp_path: Path) -> None:
    guard = IdentityCoherenceGuard(
        invariants=IdentityInvariants.from_payload(
            {
                "life_name": "Singular",
                "cardinal_values": ["integrity", "care"],
                "long_term_commitments": ["protect memory"],
            }
        ),
        root=tmp_path,
    )

    drifted = guard.evaluate_decision(
        decision={
            "life_name": "Singular",
            "values": ["integrity", "care"],
            "summary": "not protect memory",
        },
        beliefs=[{"hypothesis": "protect memory"}],
        goals=[{"objective": "not protect memory"}],
        history=[{"summary": "protect memory"}],
    )
    assert drifted.accepted is False
    assert drifted.status == "blocked"

    recovered = guard.evaluate_decision(
        decision={
            "life_name": "Singular",
            "values": ["integrity", "care"],
            "summary": "protect memory with redundant backups",
        },
        beliefs=[{"hypothesis": "protect memory"}],
        goals=[{"objective": "protect memory"}],
        history=[{"summary": "protect memory"}],
    )
    assert recovered.accepted is True
    assert recovered.status == "allowed"

    audit_path = tmp_path / "mem" / "identity_coherence_audit.jsonl"
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
