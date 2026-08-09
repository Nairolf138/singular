import pytest

from singular.life.fitness import LifecycleFitnessConfig, evaluate_mutation_fitness
from singular.life import sandbox
from singular.life.score import score
from singular.life.sandbox_scoring import (
    SandboxScore,
    classify_source_sandbox_path,
    _sandbox_failure_category,
    score_code_with_error,
)

pytestmark = pytest.mark.usefixtures("local_sandbox")


def test_technical_gain_is_rejected_when_it_destroys_health():
    weights = {
        name: 0.0
        for name in (
            "functional_gain",
            "health",
            "vital_risk",
            "resources",
            "sandbox_stability",
            "cost",
            "quest_progress",
            "identity_continuity",
            "useful_skills_retention",
        )
    }
    weights.update(functional_gain=0.3, health=0.18, vital_risk=-0.18)
    config = LifecycleFitnessConfig(weights, 2, 0.0, 0.15)
    decision = evaluate_mutation_fitness(
        {"health": 1.0, "vital_risk": 0.0},
        {"functional_gain": 1.0, "health": 0.1, "vital_risk": 0.8},
        config,
        observations=2,
    )
    assert decision.useful is True
    assert decision.accepted is False
    assert decision.viable is False
    assert "vital_regression_threshold_exceeded" in decision.rejection_reasons


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


def test_sandbox_score_finite_result_is_comparable(local_sandbox):
    result = score_code_with_error("result = 2.5")

    assert result.ok is True
    assert result.score == 2.5
    assert result.comparable_score == 2.5
    assert result.is_candidate_failure is False
    assert result.is_infrastructure_failure is False


def test_sandbox_score_non_finite_result_is_candidate_failure(local_sandbox):
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


def test_sandbox_score_execution_timeout_is_infrastructure_failure(monkeypatch):
    def fail_execution(_code: str):
        raise TimeoutError("sandbox execution timed out")

    monkeypatch.setattr(sandbox, "run", fail_execution)

    result = score_code_with_error("result = 1")

    assert result.ok is False
    assert result.error_type == "timeout"
    assert result.comparable_score is None
    assert result.is_infrastructure_failure is True
    assert result.is_candidate_failure is False


def test_sandbox_failure_category_distinguishes_base_and_mutation_failures():
    base = SandboxScore(score=float("-inf"), ok=False, error_type="syntax_error")
    mutation = SandboxScore(score=1.0)

    assert _sandbox_failure_category(
        base.is_candidate_failure, mutation.is_candidate_failure, "result = 1"
    ) == ("source_invalid", "medium", False)

    base = SandboxScore(score=1.0)
    mutation = SandboxScore(
        score=float("-inf"), ok=False, error_type="non_numeric_result"
    )

    assert _sandbox_failure_category(
        base.is_candidate_failure, mutation.is_candidate_failure, "result = 'bad'"
    ) == ("invalid_mutation", "medium", False)


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
    ) == ("invalid_mutation", "medium", False)


def test_source_path_categories_cover_missing_escape_and_symlinks(tmp_path):
    skills = tmp_path / "skills"
    skills.mkdir()
    inside = skills / "ok.py"
    inside.write_text("result = 1\n")
    outside = tmp_path.parent / "outside.py"
    outside.write_text("result = 2\n")

    assert (
        classify_source_sandbox_path(
            "skills/ok.py", (skills,), sandbox_root=tmp_path
        ).category
        is None
    )
    assert (
        classify_source_sandbox_path(
            skills / "missing.py", (skills,), sandbox_root=tmp_path
        ).category
        == "missing_artifact"
    )
    assert (
        classify_source_sandbox_path(outside, (skills,), sandbox_root=tmp_path).category
        == "confirmed_root_escape"
    )
    (skills / "out.py").symlink_to(outside)
    assert (
        classify_source_sandbox_path(
            skills / "out.py", (skills,), sandbox_root=tmp_path
        ).category
        == "outbound_symlink"
    )
    inbound = tmp_path / "inbound.py"
    inbound.symlink_to(inside)
    assert (
        classify_source_sandbox_path(inbound, (skills,), sandbox_root=tmp_path).category
        is None
    )
