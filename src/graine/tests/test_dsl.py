import pytest

from graine.evolver.dsl import (
    Patch,
    DSLValidationError,
    CYCLOMATIC_LIMIT,
    OPERATOR_NAMES,
    THETA_DIFF_LIMIT,
)
from graine.evolver.generate import propose_mutations, load_zones


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


@pytest.mark.parametrize(
    "op",
    [
        {"op": "CONST_TUNE", "delta": 0.0, "bounds": [-0.1, 0.1]},
        {"op": "EQ_REWRITE", "rule_id": "algebra.id"},
        {"op": "INLINE"},
        {"op": "EXTRACT"},
        {"op": "DEADCODE_ELIM"},
        {"op": "MICRO_MEMO"},
    ],
)
def test_dsl_accepts_all_whitelisted_ops(op):
    patch = build_patch(ops=[op])
    assert patch.validate() is True


def test_dsl_rejects_bad_operator():
    with pytest.raises(DSLValidationError):
        build_patch(ops=[{"op": "BAD_OP"}])


def test_dsl_rejects_large_theta_diff():
    patch = build_patch(theta_diff=THETA_DIFF_LIMIT + 1)
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


def test_generate_produces_valid_patches():
    patches = propose_mutations()
    zones = load_zones()
    total_ops = sum(len(z.get("operators", [])) for z in zones)
    assert len(patches) == total_ops
    for patch in patches:
        assert patch.validate() is True
        assert patch.cyclomatic <= CYCLOMATIC_LIMIT
        assert patch.ops and patch.ops[0].name in OPERATOR_NAMES
