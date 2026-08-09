import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from singular.cli import main
from singular.governance.policy import (
    AUTH_BLOCKED,
    MutationGovernancePolicy,
    classify_governance_incident,
    load_circuit_state,
)
from singular.governance.values import (
    ValuesSchemaError,
    ValueWeights,
    load_value_weights,
    validate_values_payload,
)


def test_validate_values_payload_accepts_nested_values_key() -> None:
    weights = validate_values_payload(
        {
            "values": {
                "securite": 4,
                "utilite_utilisateur": 3,
                "preservation_memoire": 2,
                "curiosite_bornee": 1,
            }
        }
    )
    assert weights.securite == pytest.approx(0.4)
    assert weights.utilite_utilisateur == pytest.approx(0.3)
    assert weights.preservation_memoire == pytest.approx(0.2)
    assert weights.curiosite_bornee == pytest.approx(0.1)


def test_validate_values_payload_rejects_invalid_schema() -> None:
    with pytest.raises(ValuesSchemaError):
        validate_values_payload({"securite": 1, "utilite_utilisateur": 1})
    with pytest.raises(ValuesSchemaError):
        validate_values_payload(
            {
                "values": {
                    "securite": -1,
                    "utilite_utilisateur": 1,
                    "preservation_memoire": 1,
                    "curiosite_bornee": 1,
                }
            }
        )
    with pytest.raises(ValuesSchemaError):
        validate_values_payload(
            {
                "values": {
                    "securite": 1,
                    "utilite_utilisateur": 1,
                    "preservation_memoire": 1,
                    "curiosite_bornee": 1,
                    "inattendu": 1,
                }
            }
        )


def test_load_value_weights_defaults_when_file_missing_or_empty(tmp_path: Path) -> None:
    assert load_value_weights(tmp_path / "missing.yaml") == ValueWeights()
    empty = tmp_path / "values.yaml"
    empty.write_text("", encoding="utf-8")
    assert load_value_weights(empty) == ValueWeights()


def test_policy_blocks_destructive_overwrite_when_memory_preservation_high(
    tmp_path: Path,
) -> None:
    root = tmp_path
    target = root / "skills" / "example.py"
    target.parent.mkdir(parents=True)
    target.write_text("x = 1\n" * 20, encoding="utf-8")

    policy = MutationGovernancePolicy(
        value_weights=ValueWeights(
            securite=0.2,
            utilite_utilisateur=0.2,
            preservation_memoire=0.8,
            curiosite_bornee=0.1,
        )
    )
    decision = policy.enforce_write(target, "x = 1\n", root=root)
    assert decision.level == AUTH_BLOCKED
    assert "memory-preservation guard" in decision.reason


def test_policy_enforces_mutation_quota(tmp_path: Path) -> None:
    target = tmp_path / "skills" / "example.py"
    policy = MutationGovernancePolicy(
        mutation_quota_per_window=1, mutation_quota_window_seconds=60.0
    )

    first = policy.enforce_write(target, "result = 1\n", root=tmp_path)
    second = policy.enforce_write(target, "result = 2\n", root=tmp_path)

    assert first.allowed is True
    assert second.allowed is False
    assert "quota exceeded" in second.reason
    assert second.severity == "medium"


def test_internal_policy_denials_do_not_open_global_breaker(tmp_path: Path) -> None:
    target = tmp_path / "skills" / "example.py"
    forbidden = tmp_path / "src" / "blocked.py"
    policy = MutationGovernancePolicy(
        circuit_breaker_threshold=2,
        circuit_breaker_window_seconds=60.0,
        circuit_breaker_cooldown_seconds=120.0,
    )

    policy.enforce_write(forbidden, "x = 1\n", root=tmp_path)
    policy.enforce_write(forbidden, "x = 2\n", root=tmp_path)
    decision = policy.enforce_write(target, "result = 42\n", root=tmp_path)

    assert policy.mutations_enabled() is True
    assert decision.allowed is True


def test_incident_scopes_only_allow_global_escape_to_open_breaker(
    tmp_path: Path,
) -> None:
    policy = MutationGovernancePolicy(
        circuit_breaker_category_thresholds={"confirmed_root_escape": 1},
        circuit_state_file=tmp_path / "mem" / "governance_circuit.json",
    )

    for category in ("invalid_mutation", "source_invalid", "infrastructure"):
        assert policy.record_violation(category=category) is None
    assert policy.circuit_breaker_state() == "closed"
    assert policy.record_violation(category="confirmed_root_escape") is not None
    assert policy.circuit_breaker_state() == "open"
    evidence = load_circuit_state(tmp_path)["violations"]["evidence"][-1]
    assert evidence["window_seconds"] == policy.circuit_breaker_window_seconds
    assert evidence["expires_at"]


def test_canonical_incident_recovery_contract() -> None:
    assert classify_governance_incident("invalid_mutation").scope == "candidate"
    assert classify_governance_incident("source_invalid").scope == "skill"
    assert classify_governance_incident("infrastructure").scope == "life"
    assert classify_governance_incident("outbound_symlink").scope == "global"


def test_policy_logs_circuit_breaker_opened_only_once_when_already_open(
    caplog: pytest.LogCaptureFixture,
) -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = {"now": start}
    policy = MutationGovernancePolicy(
        circuit_breaker_threshold=2,
        circuit_breaker_window_seconds=60.0,
        circuit_breaker_cooldown_seconds=120.0,
    )
    policy._now = lambda: clock["now"]  # type: ignore[method-assign]
    caplog.set_level(logging.ERROR, logger="singular.governance.policy")

    first = policy.record_violation(
        category="confirmed_root_escape", severity="critical"
    )
    opened = policy.record_violation(
        category="confirmed_root_escape", severity="critical"
    )
    repeated = policy.record_violation(
        category="confirmed_root_escape", severity="critical"
    )
    policy.record_violation(category="confirmed_root_escape", severity="critical")

    assert first is None
    assert opened is not None
    assert opened.category == "confirmed_root_escape"
    assert opened.severity == "critical"
    assert opened.threshold == 2
    assert opened.cooldown_seconds == 120.0
    assert opened.open_until == "2026-01-01T00:02:00+00:00"
    assert opened.corrective_action
    assert opened.to_payload()["open_until"] == opened.open_until
    assert policy.last_circuit_breaker_state() == opened
    assert repeated is None

    opened_events = [
        record
        for record in caplog.records
        if "governance circuit breaker opened" in record.message
    ]
    assert len(opened_events) == 1


def test_policy_safe_mode_blocks_writes(tmp_path: Path) -> None:
    target = tmp_path / "skills" / "example.py"
    policy = MutationGovernancePolicy(safe_mode=True)

    decision = policy.enforce_write(target, "result = 1\n", root=tmp_path)

    assert decision.allowed is False
    assert decision.severity == "high"
    assert "safe-mode" in decision.reason


def test_policy_blocks_blacklisted_runtime_capability(tmp_path: Path) -> None:
    policy = MutationGovernancePolicy(
        runtime_blacklisted_capabilities=("network",),
        safe_mode=False,
    )
    decision = policy.evaluate_skill_execution(
        skill_name="network.fetch",
        capability="network",
    )
    assert decision.allowed is False
    assert decision.level == AUTH_BLOCKED
    assert "blacklisted" in decision.reason


def test_skill_circuit_breaker_cooldown_and_reactivation_controlled(
    tmp_path: Path,
) -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = {"now": start}
    policy = MutationGovernancePolicy(
        skill_circuit_breaker_failure_threshold=2,
        skill_circuit_breaker_cooldown_seconds=30.0,
        auto_rollback_failure_threshold=2,
        safe_mode=False,
    )
    policy._now = lambda: clock["now"]  # type: ignore[method-assign]
    skill = "math.addition"

    first = policy.evaluate_skill_execution(skill_name=skill, capability="compute")
    assert first.allowed is True
    policy.record_skill_execution(skill_name=skill, success=False, operation_cost=0.5)
    policy.record_skill_execution(skill_name=skill, success=False, operation_cost=0.5)

    blocked = policy.evaluate_skill_execution(skill_name=skill, capability="compute")
    assert blocked.allowed is False
    assert "circuit-breaker active" in blocked.reason
    assert policy.skill_reactivation_allowed(skill) is False

    clock["now"] = start + timedelta(seconds=31)
    half_open = policy.evaluate_skill_execution(skill_name=skill, capability="compute")
    assert half_open.allowed is False
    assert policy.record_safe_probe(success=True, responsible=skill) is True
    assert (
        policy.evaluate_skill_execution(skill_name=skill, capability="compute").allowed
        is True
    )


def test_policy_safe_mode_requires_review_for_sensitive_skill_family(
    tmp_path: Path,
) -> None:
    policy = MutationGovernancePolicy(
        safe_mode=True,
        safe_mode_review_required_skill_families=("network", "shell"),
        runtime_blacklisted_capabilities=(),
    )
    decision = policy.evaluate_skill_execution(
        skill_name="network.fetch",
        capability="compute",
    )
    assert decision.allowed is False
    assert decision.level == "review-required"
    assert "safe-mode requires manual review" in decision.reason


def test_policy_blocks_explicit_hostile_interlife_behavior(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))
    policy = MutationGovernancePolicy()

    decision = policy.record_interlife_interaction(
        source_life="alpha",
        target_life="beta",
        interaction="threat.explicit",
        influence_delta=0.1,
    )

    assert decision.allowed is False
    assert decision.level == AUTH_BLOCKED
    journal = tmp_path / "mem" / "policy_decisions.jsonl"
    lines = journal.read_text(encoding="utf-8").strip().splitlines()
    assert lines
    payload = json.loads(lines[-1])
    assert payload["category"] == "inter_life"
    assert "hostile behavior" in payload["reason"]


def test_policy_conflict_threshold_triggers_mediation_and_prudent_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))
    policy = MutationGovernancePolicy()

    for _ in range(policy.social_conflict_mediation_threshold):
        decision = policy.record_interlife_interaction(
            source_life="alpha",
            target_life="beta",
            interaction="resource_conflict",
            influence_delta=0.0,
        )
        assert decision.allowed is True

    blocked = policy.record_interlife_interaction(
        source_life="alpha",
        target_life="beta",
        interaction="help.transfer",
        influence_delta=0.01,
    )
    assert blocked.allowed is False
    assert "mediation cooldown" in blocked.reason
    assert policy.social_prudent_mode_enabled() is True


def test_cli_values_show_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    root = tmp_path / "root"
    monkeypatch.delenv("SINGULAR_ROOT", raising=False)
    monkeypatch.delenv("SINGULAR_HOME", raising=False)

    main(["--root", str(root), "lives", "create", "--name", "Alpha"])
    capsys.readouterr()
    code = main(["--root", str(root), "--format", "json", "values", "show"])
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    assert code == 0
    assert set(payload["values"].keys()) == {
        "securite",
        "utilite_utilisateur",
        "preservation_memoire",
        "curiosite_bornee",
    }


def test_cli_policy_show_and_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    root = tmp_path / "root"
    monkeypatch.delenv("SINGULAR_ROOT", raising=False)
    monkeypatch.delenv("SINGULAR_HOME", raising=False)

    code_show = main(["--root", str(root), "--format", "json", "policy", "show"])
    output = capsys.readouterr().out.strip().splitlines()
    payload = json.loads(output[-1])
    assert code_show == 0
    assert payload["policy"]["version"] == 1
    assert "impact" in payload["policy"]

    code_set = main(
        [
            "--root",
            str(root),
            "policy",
            "set",
            "--key",
            "autonomy.safe_mode",
            "--value",
            "true",
        ]
    )
    out = capsys.readouterr().out
    assert code_set == 0
    assert "Politique mise à jour" in out
