import json
import pytest

from singular.life import quest


def test_load_valid_spec(tmp_path):
    spec_data = {
        "name": "adder",
        "signature": "adder(a, b)",
        "examples": [{"input": [1, 2], "output": 3}],
        "constraints": {"pure": True, "no_import": True, "time_ms_max": 50},
    }
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec_data), encoding="utf-8")
    spec = quest.load(path)
    assert spec.name == "adder"
    assert spec.signature == "adder(a, b)"
    assert spec.constraints.time_ms_max == 50
    assert spec.triggers == []
    assert spec.reward == {}
    assert spec.penalty == {}
    assert spec.cooldown == 0


def test_load_extended_quest_fields(tmp_path):
    spec_data = {
        "name": "repair_loop",
        "signature": "repair_loop(x)",
        "examples": [{"input": [1], "output": 1}],
        "constraints": {"pure": True, "no_import": True, "time_ms_max": 25},
        "triggers": [{"signal": "noise", "gte": 0.5}],
        "reward": {"mood": "pleasure", "resource_delta": {"food": 2}},
        "penalty": {"mood": "pain", "resource_delta": {"energy": -1}},
        "cooldown": 60,
        "success": {"resource_min": {"energy": 80}},
    }
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec_data), encoding="utf-8")

    spec = quest.load(path)

    assert spec.triggers == [{"signal": "noise", "gte": 0.5}]
    assert spec.reward["mood"] == "pleasure"
    assert spec.penalty["mood"] == "pain"
    assert spec.cooldown == 60


@pytest.mark.parametrize(
    "constraints",
    [
        {"pure": "yes", "no_import": True, "time_ms_max": 10},
        {"pure": True, "no_import": True, "time_ms_max": -1},
        {"pure": True},
    ],
)
def test_load_invalid_constraints(tmp_path, constraints):
    spec_data = {
        "name": "adder",
        "signature": "adder(a, b)",
        "examples": [{"input": [1, 2], "output": 3}],
        "constraints": constraints,
    }
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec_data), encoding="utf-8")
    with pytest.raises(quest.SpecValidationError):
        quest.load(path)
