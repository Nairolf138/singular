import json
from pathlib import Path

import pytest
from fastapi_stub import TestClient

from singular.dashboard import create_app
from singular.evaluation import run_multi_life_evaluation


def test_offline_multi_life_replays_trace_and_exposes_ablation_effects(
    tmp_path: Path,
) -> None:
    config = tmp_path / "agi_kpis.yaml"
    config.write_text("minimum_observable_effect: 0.05\n", encoding="utf-8")
    output = tmp_path / "artifact.json"
    result = run_multi_life_evaluation(
        seeds=[11, 23, 37, 53, 71], output=output, kpi_config=config
    )
    assert result["offline"] is True
    assert result["dashboard_summary"]["status"] == "pass"
    assert all(
        item["observable"] for item in result["negative_control_comparisons"].values()
    )
    assert {
        len(group["lives"][0]["decisions"]) for group in result["groups"].values()
    } == {8}
    assert json.loads(output.read_text())["schema_version"].endswith("/v1")


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
