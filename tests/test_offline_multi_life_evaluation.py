import json
from pathlib import Path

import pytest
from fastapi_stub import TestClient

from singular.dashboard import create_app
from singular.evaluation import run_multi_life_evaluation


def test_offline_multi_life_artifact_schema_and_blocking_criteria(
    tmp_path: Path,
) -> None:
    config = tmp_path / "agi_kpis.yaml"
    config.write_text("minimum_health_delta: 0.0\n", encoding="utf-8")
    output = tmp_path / "artifact.json"
    result = run_multi_life_evaluation(
        seeds=[11, 23, 37, 53, 71], output=output, kpi_config=config
    )
    assert result["offline"] is True
    assert result["dashboard_summary"]["status"] == "pass"
    assert result["schema_version"].endswith("/v2")
    assert result["protocol_version"] == "ada-bob-eve/1.0.0"
    assert result["scenarios"] == [
        {"id": "ada", "version": "1.0.0"},
        {"id": "bob", "version": "1.1.0"},
        {"id": "eve", "version": "2.0.0"},
    ]
    assert len(result["runs"]) == 15
    required_snapshot_fields = {
        "configuration",
        "seed",
        "life_id",
        "vital_status",
        "health",
        "risk",
        "resources",
        "cognition",
        "beliefs",
        "traits",
        "quests",
        "narration",
        "embodiment_events",
        "mutations",
        "circuit_breaker",
    }
    for run in result["runs"]:
        assert required_snapshot_fields == set(run["before"])
        assert required_snapshot_fields == set(run["after"])
        assert all(run["blocking_criteria"].values())
        assert run["before"]["life_id"] == run["after"]["life_id"]
    for summary in result["summary"]["by_scenario"].values():
        for metric in ("health_delta", "risk_delta", "mutation_utility"):
            assert set(summary[metric]) == {
                "median",
                "dispersion",
                "interval",
                "sample_size",
            }
            assert set(summary[metric]["interval"]) == {"low", "high"}
    assert json.loads(output.read_text()) == result


def test_offline_multi_life_is_byte_deterministic(tmp_path: Path) -> None:
    config = tmp_path / "kpi.yaml"
    config.write_text("minimum_useful_mutation_delta: 0.01\n", encoding="utf-8")
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    kwargs = {"seeds": [11, 23, 37], "kpi_config": config}
    first_result = run_multi_life_evaluation(output=first, **kwargs)
    second_result = run_multi_life_evaluation(output=second, **kwargs)
    assert first_result == second_result
    assert first.read_bytes() == second.read_bytes()


def test_offline_multi_life_requires_distinct_seeds(tmp_path: Path) -> None:
    config = tmp_path / "kpi.yaml"
    config.write_text("")
    with pytest.raises(ValueError, match="distinct"):
        run_multi_life_evaluation(
            seeds=[1, 1], output=tmp_path / "x.json", kpi_config=config
        )


def test_dashboard_reads_compact_evaluation_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "artifacts/evaluations/offline_multi_life_v1.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(
        json.dumps(
            {
                "schema_version": "singular.offline-multi-life-evaluation/v1",
                "generated_at": "2026-08-07T00:00:00+00:00",
                "dashboard_summary": {"status": "pass", "headline": "offline"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))
    payload = (
        TestClient(create_app(psyche_file=tmp_path / "psyche.json"))
        .get("/api/evaluations/offline-multi-life")
        .json()
    )
    assert payload["available"] is True
    assert payload["summary"] == {"status": "pass", "headline": "offline"}
