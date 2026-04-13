from pathlib import Path
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
