from pathlib import Path
from datetime import datetime, timedelta, timezone
import json

import pytest

from singular.cli import main
from singular.governance.policy import AUTH_BLOCKED, MutationGovernancePolicy
from singular.governance.values import (
    ValueWeights,
    ValuesSchemaError,
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


def test_policy_blocks_destructive_overwrite_when_memory_preservation_high(tmp_path: Path) -> None:
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
    policy = MutationGovernancePolicy(mutation_quota_per_window=1, mutation_quota_window_seconds=60.0)

    first = policy.enforce_write(target, "result = 1\n", root=tmp_path)
    second = policy.enforce_write(target, "result = 2\n", root=tmp_path)

    assert first.allowed is True
    assert second.allowed is False
    assert "quota exceeded" in second.reason
    assert second.severity == "medium"


def test_policy_opens_circuit_breaker_on_repeated_violations(tmp_path: Path) -> None:
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

    assert policy.mutations_enabled() is False
    assert decision.allowed is False
    assert "circuit-breaker active" in decision.reason
    assert decision.severity == "critical"


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


def test_skill_circuit_breaker_cooldown_and_reactivation_controlled(tmp_path: Path) -> None:
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
    allowed = policy.evaluate_skill_execution(skill_name=skill, capability="compute")
    assert allowed.allowed is True
    assert policy.skill_reactivation_allowed(skill) is True


def test_policy_safe_mode_requires_review_for_sensitive_skill_family(tmp_path: Path) -> None:
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


def test_cli_values_show_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
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


def test_cli_policy_show_and_set(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
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
