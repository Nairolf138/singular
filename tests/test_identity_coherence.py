import json
import pytest
from pathlib import Path

from singular.identity import (
    IdentityCoherenceGuard,
    IdentityInvariants,
    detect_contradictions,
)


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
    assert any(
        "cardinal_values_missing" in item for item in decision.invariant_violations
    )
    assert any(
        "long_term_commitment_negated" in item for item in decision.invariant_violations
    )

    audit_path = tmp_path / "mem" / "identity_coherence_audit.jsonl"
    entries = [
        json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()
    ]
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


def test_identity_sync_projects_multi_event_versions(tmp_path):
    from singular.identity.synchronization import IdentitySynchronizationService

    service = IdentitySynchronizationService(tmp_path)
    first = service.apply_event(
        {"event_id": "one", "source": "test", "deltas": {"optimism": 0.1}}
    )
    second = service.apply_event(
        {"event_id": "two", "source": "test", "deltas": {"patience": -0.1}}
    )

    psyche = json.loads((tmp_path / "mem" / "psyche.json").read_text())
    narrative = json.loads((tmp_path / "mem" / "self_narrative.json").read_text())
    assert (first.psyche_version, second.psyche_version) == (1, 2)
    assert narrative["psyche_version"] == psyche["psyche_version"] == 2
    assert narrative["narrative_version"] == 2
    assert narrative["last_event_id"] == "two"


def test_identity_sync_recovers_partial_write_without_publishing(monkeypatch, tmp_path):
    import singular.identity.synchronization as sync_module
    from singular.events import EventBus
    from singular.identity.synchronization import IdentitySynchronizationService

    events = []
    bus = EventBus()
    bus.subscribe("self_narrative.updated", lambda event: events.append(event.payload))
    service = IdentitySynchronizationService(tmp_path, bus=bus)
    original = sync_module.atomic_write_text
    failed = False

    def fail_narrative(path, data, *args, **kwargs):
        nonlocal failed
        if str(path).endswith("self_narrative.json") and not failed:
            failed = True
            raise OSError("simulated narrative failure")
        return original(path, data, *args, **kwargs)

    monkeypatch.setattr(sync_module, "atomic_write_text", fail_narrative)
    with pytest.raises(OSError):
        service.apply_event(
            {"event_id": "partial", "source": "test", "deltas": {"curiosity": 0.1}}
        )
    assert events == []
    assert service.journal_path.exists()

    monkeypatch.setattr(sync_module, "atomic_write_text", original)
    recovered = service.recover()
    assert recovered is not None and recovered.recovered
    psyche = json.loads(service.psyche_path.read_text())
    narrative = json.loads(service.narrative_path.read_text())
    assert psyche["psyche_version"] == narrative["psyche_version"] == 1
