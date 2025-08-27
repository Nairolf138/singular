import pytest

from graine.evolver.dsl import (
    Patch,
    DSLValidationError,
)


def build_patch(**overrides):
    data = {
        "type": "Patch",
        "target": {"file": "dummy.py", "function": "foo"},
        "ops": [{"op": "CONST_TUNE", "delta": 0.0, "bounds": [-0.1, 0.1]}],
        "theta_diff": 1,
        "purity": True,
        "cyclomatic": 1,
    }
    data.update(overrides)
    return Patch.from_dict(data)


def test_dsl_accepts_valid_patch():
    patch = build_patch()
    assert patch.validate() is True


def test_dsl_rejects_bad_operator():
    data = {
        "type": "Patch",
        "target": {"file": "dummy.py", "function": "foo"},
        "ops": [{"op": "BAD_OP"}],
        "theta_diff": 1,
        "purity": True,
        "cyclomatic": 1,
    }
    with pytest.raises(DSLValidationError):
        Patch.from_dict(data)


def test_dsl_rejects_large_theta_diff():
    patch = build_patch(theta_diff=50)
    with pytest.raises(DSLValidationError):
        patch.validate()


def test_dsl_rejects_impure_patch():
    patch = build_patch(purity=False)
    with pytest.raises(DSLValidationError):
        patch.validate()


def test_dsl_rejects_high_cyclomatic():
    patch = build_patch(cyclomatic=50)
    with pytest.raises(DSLValidationError):
        patch.validate()
