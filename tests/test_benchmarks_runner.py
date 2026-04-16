from __future__ import annotations

import json
from pathlib import Path

import pytest

from singular.benchmarks.runner import BenchmarkRegressionError, run_benchmarks


def _write_domain(path: Path, domain: str, candidate: str) -> None:
    payload = {
        "domain": domain,
        "cases": [
            {
                "id": f"{domain}_1",
                "prompt": "p",
                "reference_keywords": ["alpha", "beta"],
                "candidate_answer": candidate,
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_run_benchmarks_writes_artifacts_and_summary(tmp_path: Path) -> None:
    benchmarks_dir = tmp_path / "benchmarks"
    artifacts_dir = tmp_path / "artifacts"
    summary_path = tmp_path / "mem" / "benchmark_summary.json"
    weights_path = benchmarks_dir / "weights.json"

    benchmarks_dir.mkdir()
    for domain in ["raisonnement", "code", "planification", "memoire", "interaction", "adaptation"]:
        _write_domain(benchmarks_dir / f"{domain}.json", domain, "alpha beta")

    weights_path.write_text(
        json.dumps(
            {
                "raisonnement": 2,
                "code": 2,
                "planification": 1,
                "memoire": 1,
                "interaction": 1,
                "adaptation": 1,
            }
        ),
        encoding="utf-8",
    )

    result = run_benchmarks(
        benchmarks_dir=benchmarks_dir,
        artifacts_dir=artifacts_dir,
        summary_path=summary_path,
        weights_path=weights_path,
        max_regression_drop=0.05,
    )

    assert result["global_score"] == 1.0
    assert set(result["domain_scores"]) == {
        "raisonnement",
        "code",
        "planification",
        "memoire",
        "interaction",
        "adaptation",
    }

    for domain in result["domain_scores"]:
        artifact_path = artifacts_dir / f"{domain}.json"
        assert artifact_path.exists()
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == "1.0"
        assert payload["domain"] == domain
        assert payload["case_count"] == 1

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["global_score"] == 1.0
    assert summary["non_regression"]["status"] == "passed"


def test_run_benchmarks_fails_on_regression(tmp_path: Path) -> None:
    benchmarks_dir = tmp_path / "benchmarks"
    artifacts_dir = tmp_path / "artifacts"
    summary_path = tmp_path / "mem" / "benchmark_summary.json"

    benchmarks_dir.mkdir()
    for domain in ["raisonnement", "code", "planification", "memoire", "interaction", "adaptation"]:
        _write_domain(benchmarks_dir / f"{domain}.json", domain, "alpha beta")

    run_benchmarks(
        benchmarks_dir=benchmarks_dir,
        artifacts_dir=artifacts_dir,
        summary_path=summary_path,
        weights_path=benchmarks_dir / "weights.json",
        max_regression_drop=0.01,
    )

    for domain in ["raisonnement", "code", "planification", "memoire", "interaction", "adaptation"]:
        _write_domain(benchmarks_dir / f"{domain}.json", domain, "alpha")

    with pytest.raises(BenchmarkRegressionError):
        run_benchmarks(
            benchmarks_dir=benchmarks_dir,
            artifacts_dir=artifacts_dir,
            summary_path=summary_path,
            weights_path=benchmarks_dir / "weights.json",
            max_regression_drop=0.01,
        )
