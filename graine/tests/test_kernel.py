import pytest

from graine.kernel import run_variant, VerificationError
from graine.kernel import verifier


def test_load_objectives_parses_config():
    obj = verifier.load_objectives()
    assert obj["perf"]["repetitions"] == 21


def test_load_objectives_invalid(tmp_path):
    bad = tmp_path / "objectives.yaml"
    bad.write_text("perf:\n  target_improvement_pct: 5\n")
    with pytest.raises(VerificationError):
        verifier.load_objectives(str(bad))


def test_load_operators_parses_config():
    ops = verifier.load_operators()
    assert "CONST_TUNE" in ops


def test_load_operators_invalid(tmp_path):
    bad = tmp_path / "operators.yaml"
    bad.write_text("CONST_TUNE:\n  something: 1\n")
    with pytest.raises(VerificationError):
        verifier.load_operators(str(bad))


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


def test_run_variant_times_out():
    patch = {
        "type": "Patch",
        "target": {"file": "target/src/algorithms/reduce_sum.py", "function": "reduce_sum"},
        "ops": [
            {"op": "CONST_TUNE", "delta": 0.0, "bounds": [-0.1, 0.1]},
        ],
        "limits": {"diff_max": 5, "cpu": 0.0},
    }
    with pytest.raises(RuntimeError):
        run_variant(patch)


def test_run_variant_op_limit():
    patch = {
        "type": "Patch",
        "target": {"file": "target/src/algorithms/reduce_sum.py", "function": "reduce_sum"},
        "ops": [
            {"op": "CONST_TUNE", "delta": 0.0, "bounds": [-0.1, 0.1]},
            {"op": "CONST_TUNE", "delta": 0.0, "bounds": [-0.1, 0.1]},
        ],
        "limits": {"diff_max": 5, "ops": 1},
    }
    with pytest.raises(RuntimeError):
        run_variant(patch)


def _inline_patch(code: str) -> dict:
    return {
        "type": "Patch",
        "target": {"file": "target/src/algorithms/reduce_sum.py", "function": "reduce_sum"},
        "ops": [{"op": "INLINE", "code": code}],
        "limits": {"diff_max": 5},
    }


def test_verify_rejects_network_import():
    patch = _inline_patch("import socket")
    with pytest.raises(VerificationError):
        run_variant(patch)


def test_verify_rejects_ffi_import():
    patch = _inline_patch("import ctypes")
    with pytest.raises(VerificationError):
        run_variant(patch)


def test_verify_rejects_subprocess_import():
    patch = _inline_patch("import subprocess")
    with pytest.raises(VerificationError):
        run_variant(patch)


def test_verify_rejects_outside_io():
    patch = _inline_patch("open('evil.txt', 'w')")
    with pytest.raises(VerificationError):
        run_variant(patch)


def _limit_patch() -> dict:
    return {
        "type": "Patch",
        "target": {"file": "target/src/algorithms/reduce_sum.py", "function": "reduce_sum"},
        "ops": [{"op": "INLINE"}],
        "limits": {"diff_max": 5},
    }


def test_verify_rejects_ops_quota():
    patch = _limit_patch()
    patch["limits"]["ops"] = 2000
    with pytest.raises(VerificationError):
        run_variant(patch)


def test_verify_rejects_cpu_quota():
    patch = _limit_patch()
    patch["limits"]["cpu"] = 2.0
    with pytest.raises(VerificationError):
        run_variant(patch)


def test_verify_rejects_time_max():
    patch = _limit_patch()
    patch["limits"]["time_max"] = 2.0
    with pytest.raises(VerificationError):
        run_variant(patch)


def test_verify_rejects_ram_quota():
    patch = _limit_patch()
    patch["limits"]["ram"] = 10**10
    with pytest.raises(VerificationError):
        run_variant(patch)


def test_run_variant_hard_timeout_signal():
    patch = {
        "type": "Patch",
        "target": {"file": "target/src/algorithms/reduce_sum.py", "function": "reduce_sum"},
        "ops": [
            {"op": "INLINE", "sleep": 1.0},
        ],
        "limits": {"diff_max": 5, "cpu": 0.1},
    }
    with pytest.raises(RuntimeError):
        run_variant(patch)


def test_run_variant_memory_limit_exceeded():
    patch = {
        "type": "Patch",
        "target": {"file": "target/src/algorithms/reduce_sum.py", "function": "reduce_sum"},
        "ops": [
            {"op": "INLINE", "size": 300 * 1024 * 1024},
        ],
        "limits": {"diff_max": 5},
    }
    with pytest.raises(RuntimeError):
        run_variant(patch)
