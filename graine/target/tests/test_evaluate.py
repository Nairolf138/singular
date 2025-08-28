from graine.target.src import evaluate
from graine.target.src.algorithms.reduce_sum import reduce_sum


# Helper benchmark to keep tests fast


def _fast_benchmark(
    func,
    data,
    runs=21,
    warmups=0,
    bootstrap_samples=1000,
    cpu=None,
):
    return {"median": 0.0, "iqr": 0.0, "ic95": (0.0, 0.0)}


def _stub_diff_test(baseline, variant, cases=100):
    return {"equivalent": True, "mismatches": []}


# Unit and integration tests for evaluate()


def test_evaluate_success(monkeypatch):
    monkeypatch.setattr(evaluate, "benchmark", _fast_benchmark)
    monkeypatch.setattr(evaluate, "diff_test", _stub_diff_test)
    result = evaluate.evaluate(reduce_sum)
    assert result["functional_pass"]
    assert result["security_pass"]
    assert result["robustness"]["pass_rate"] == 1.0
    assert "performance" in result


def test_evaluate_robustness_failure(monkeypatch):
    monkeypatch.setattr(evaluate, "benchmark", _fast_benchmark)
    monkeypatch.setattr(evaluate, "diff_test", _stub_diff_test)

    def bad_candidate(values):
        return sum(values) + 1

    result = evaluate.evaluate(bad_candidate)
    assert not result["functional_pass"]
    assert result["robustness"]["pass_rate"] < 1.0


# Tests for diff-testing


def baseline(xs):
    return sum(xs)


def variant_ok(xs):
    return sum(xs)


def variant_bug(xs):
    return sum(xs) + 1


def variant_error(xs):
    raise ValueError("boom")


def baseline_error(xs):
    raise RuntimeError("oops")


def test_diff_test_equivalent():
    res = evaluate.diff_test(baseline, variant_ok, cases=5)
    assert res["equivalent"]
    assert res["mismatches"] == []


def test_diff_test_mismatch():
    res = evaluate.diff_test(baseline, variant_bug, cases=5)
    assert not res["equivalent"]
    assert res["mismatches"]


def test_diff_test_variant_error():
    res = evaluate.diff_test(baseline, variant_error, cases=1)
    assert not res["equivalent"]
    assert "variant_error" in res["mismatches"][0]


def test_diff_test_baseline_error():
    res = evaluate.diff_test(baseline_error, variant_ok, cases=1)
    assert not res["equivalent"]
    assert "baseline_error" in res["mismatches"][0]
