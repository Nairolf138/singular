from singular.life.score import score


def test_score_single_run_variance_zero():
    value, var = score("result = 1", runs=1)
    assert isinstance(value, float)
    assert var == 0.0


def test_complexity_penalty_increases_score():
    simple = "result = 1"
    complex_code = "result = 0\nfor i in range(1000):\n    result += i\n"
    simple_score, _ = score(simple, runs=1, alpha=100.0)
    complex_score, _ = score(complex_code, runs=1, alpha=100.0)
    assert complex_score > simple_score

from singular.life import sandbox
from singular.life.sandbox_scoring import (
    SandboxScore,
    _sandbox_failure_category,
    score_code_with_error,
)


def test_sandbox_score_finite_result_is_comparable():
    result = score_code_with_error("result = 2.5")

    assert result.ok is True
    assert result.score == 2.5
    assert result.comparable_score == 2.5
    assert result.is_candidate_failure is False
    assert result.is_infrastructure_failure is False


def test_sandbox_score_non_finite_result_is_candidate_failure():
    result = score_code_with_error("result = 1e309")

    assert result.ok is False
    assert result.score == float("-inf")
    assert result.error_type == "non_finite_result"
    assert result.comparable_score is None
    assert result.is_candidate_failure is True
    assert result.is_infrastructure_failure is False


def test_sandbox_score_startup_timeout_is_infrastructure_failure(monkeypatch):
    def fail_startup(_code: str):
        raise TimeoutError("sandbox process startup timed out")

    monkeypatch.setattr(sandbox, "run", fail_startup)

    result = score_code_with_error("result = 1")

    assert result.ok is False
    assert result.error_type == "sandbox_startup_timeout"
    assert result.comparable_score is None
    assert result.is_infrastructure_failure is True
    assert result.is_candidate_failure is False


def test_sandbox_failure_category_distinguishes_base_and_mutation_failures():
    base = SandboxScore(score=float("-inf"), ok=False, error_type="syntax_error")
    mutation = SandboxScore(score=1.0)

    assert _sandbox_failure_category(
        base.is_candidate_failure, mutation.is_candidate_failure, "result = 1"
    ) == ("source_sandbox_violation", "critical", True)

    base = SandboxScore(score=1.0)
    mutation = SandboxScore(
        score=float("-inf"), ok=False, error_type="non_numeric_result"
    )

    assert _sandbox_failure_category(
        base.is_candidate_failure, mutation.is_candidate_failure, "result = 'bad'"
    ) == ("invalid_mutation_rejected", "medium", False)


def test_double_failure_is_not_comparable():
    base = SandboxScore(score=float("-inf"), ok=False, error_type="missing_result")
    mutation = SandboxScore(
        score=float("-inf"), ok=False, error_type="non_numeric_result"
    )

    assert base.comparable_score is None
    assert mutation.comparable_score is None
    assert not (
        base.comparable_score is not None and mutation.comparable_score is not None
    )


def test_loop_retries_infrastructure_base_failure_without_penalty():
    from singular.life.loop import (
        _sandbox_failure_category,
        _should_retry_sandbox_scoring,
    )

    base = SandboxScore(
        score=float("-inf"), ok=False, error_type="sandbox_worker_no_payload"
    )
    mutation = SandboxScore(score=1.0)

    assert _should_retry_sandbox_scoring(base, mutation) is True
    assert _sandbox_failure_category(
        base.is_candidate_failure, mutation.is_candidate_failure, "result = 1"
    ) == (None, None, False)


def test_loop_rejects_candidate_mutation_failure_without_global_breaker():
    from singular.life.loop import (
        _sandbox_failure_category,
        _should_retry_sandbox_scoring,
    )

    base = SandboxScore(score=1.0)
    mutation = SandboxScore(
        score=float("-inf"), ok=False, error_type="non_numeric_result"
    )

    assert _should_retry_sandbox_scoring(base, mutation) is False
    assert _sandbox_failure_category(
        base.is_candidate_failure, mutation.is_candidate_failure, "result = 'bad'"
    ) == ("invalid_mutation_rejected", "medium", False)
