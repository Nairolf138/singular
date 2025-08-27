import pytest

from graine.kernel import run_variant, VerificationError


def test_verify_accepts_valid_patch():
    patch = {
        "type": "Patch",
        "target": {"file": "target/src/algorithms/reduce_sum.py", "function": "reduce_sum"},
        "ops": [
            {"op": "CONST_TUNE", "delta": 0.0, "bounds": [-0.1, 0.1]},
        ],
        "limits": {"diff_max": 5},
    }
    result = run_variant(patch)
    assert result["status"] == "validated"


def test_verify_rejects_bad_operator():
    patch = {
        "type": "Patch",
        "target": {"file": "target/src/algorithms/reduce_sum.py", "function": "reduce_sum"},
        "ops": [
            {"op": "BAD_OP"},
        ],
        "limits": {"diff_max": 5},
    }
    with pytest.raises(VerificationError):
        run_variant(patch)


def test_verify_rejects_large_diff():
    patch = {
        "type": "Patch",
        "target": {"file": "target/src/algorithms/reduce_sum.py", "function": "reduce_sum"},
        "ops": [
            {"op": "EQ_REWRITE", "rule_id": "algebra.sum.reassociate.v1"},
        ],
        "limits": {"diff_max": 20},
    }
    with pytest.raises(VerificationError):
        run_variant(patch)
