from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class BenchmarkRegressionError(RuntimeError):
    """Raised when benchmark score regression exceeds threshold."""


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _token_score(candidate: str, keywords: list[str]) -> float:
    if not keywords:
        return 1.0

    candidate_text = candidate.lower()
    hits = 0
    for keyword in keywords:
        if keyword.lower() in candidate_text:
            hits += 1

    return hits / len(keywords)


def _load_weights(weights_path: Path, domains: list[str]) -> dict[str, float]:
    if weights_path.exists():
        loaded = _load_json(weights_path)
    else:
        loaded = {}

    if not loaded:
        return {domain: 1.0 / len(domains) for domain in domains}

    total = sum(float(loaded.get(domain, 0.0)) for domain in domains)
    if total <= 0:
        return {domain: 1.0 / len(domains) for domain in domains}

    return {domain: float(loaded.get(domain, 0.0)) / total for domain in domains}


def run_benchmarks(
    benchmarks_dir: Path,
    artifacts_dir: Path,
    summary_path: Path,
    weights_path: Path,
    max_regression_drop: float,
) -> dict:
    benchmark_files = sorted(
        path
        for path in benchmarks_dir.glob("*.json")
        if path.name not in {"weights.json"}
    )

    if len(benchmark_files) < 6:
        raise ValueError("At least 6 benchmark domains are required.")

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    per_domain_scores: dict[str, float] = {}
    domain_artifacts: list[dict] = []

    for benchmark_file in benchmark_files:
        benchmark_def = _load_json(benchmark_file)
        domain = benchmark_def["domain"]
        cases = benchmark_def.get("cases", [])

        scored_cases = []
        for case in cases:
            score = _token_score(
                case.get("candidate_answer", ""),
                case.get("reference_keywords", []),
            )
            scored_cases.append(
                {
                    "id": case["id"],
                    "prompt": case.get("prompt", ""),
                    "score": round(score, 4),
                    "max_score": 1.0,
                }
            )

        domain_score = (
            sum(case["score"] for case in scored_cases) / len(scored_cases)
            if scored_cases
            else 0.0
        )
        per_domain_scores[domain] = round(domain_score, 4)

        artifact = {
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "domain": domain,
            "score": round(domain_score, 4),
            "case_count": len(scored_cases),
            "cases": scored_cases,
        }
        domain_artifacts.append(artifact)

        artifact_path = artifacts_dir / f"{domain}.json"
        with artifact_path.open("w", encoding="utf-8") as handle:
            json.dump(artifact, handle, ensure_ascii=False, indent=2)
            handle.write("\n")

    weights = _load_weights(weights_path=weights_path, domains=sorted(per_domain_scores))
    global_score = sum(per_domain_scores[d] * weights[d] for d in per_domain_scores)
    global_score = round(global_score, 4)

    previous_global_score = None
    if summary_path.exists():
        try:
            previous_global_score = float(_load_json(summary_path).get("global_score"))
        except (ValueError, TypeError, json.JSONDecodeError):
            previous_global_score = None

    drop = 0.0
    regression_failed = False
    if previous_global_score is not None:
        drop = round(previous_global_score - global_score, 4)
        regression_failed = drop > max_regression_drop

    summary = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "global_score": global_score,
        "domain_scores": per_domain_scores,
        "weights": weights,
        "non_regression": {
            "max_allowed_drop": max_regression_drop,
            "previous_global_score": previous_global_score,
            "drop": drop,
            "status": "failed" if regression_failed else "passed",
        },
    }

    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    if regression_failed:
        raise BenchmarkRegressionError(
            f"Global score regression {drop:.4f} exceeds threshold {max_regression_drop:.4f}."
        )

    return {
        "global_score": global_score,
        "domain_scores": per_domain_scores,
        "artifacts": domain_artifacts,
    }
