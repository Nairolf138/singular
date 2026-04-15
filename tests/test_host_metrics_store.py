from __future__ import annotations

import json

from singular.sensors.host_metrics_store import (
    append_host_metrics_sample,
    compute_host_metrics_aggregates,
    host_metrics_file,
    summarize_environmental_impact,
)


def test_host_metrics_store_writes_jsonl_with_retention(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))
    monkeypatch.setenv("SINGULAR_HOST_METRICS_RETENTION_SAMPLES", "3")

    for idx in range(5):
        append_host_metrics_sample(
            {
                "cpu_percent": 10 + idx,
                "ram_used_percent": 20 + idx,
                "disk_used_percent": 30 + idx,
            }
        )

    lines = host_metrics_file().read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    latest = json.loads(lines[-1])
    assert latest["metrics"]["cpu_percent"] == 14.0
    assert "metric_status" in latest


def test_host_metrics_aggregates_and_impact(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))
    monkeypatch.setenv("SINGULAR_HOST_METRICS_RETENTION_SAMPLES", "200")

    for idx in range(30):
        append_host_metrics_sample(
            {
                "cpu_percent": 70 + (idx % 5),
                "ram_used_percent": 65 + (idx % 4),
                "host_temperature_c": 72 + (idx % 3),
            }
        )

    aggregates = compute_host_metrics_aggregates()
    impact = summarize_environmental_impact(aggregates)
    assert aggregates["sample_count"] == 30
    assert aggregates["rolling_means"]["cpu_percent"]["20"] >= 70.0
    assert impact["impact_level"] in {"moderate", "high", "critical"}
    assert impact["decision_bias"] == "robustesse"


def test_host_metrics_store_accepts_metric_status_payload(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))
    append_host_metrics_sample(
        {
            "cpu_percent": {
                "value": 42.0,
                "unit": "percent",
                "status": "available",
                "reason": None,
                "last_seen_at": "2026-01-01T00:00:00+00:00",
            },
            "ram_used_percent": 55.0,
            "metric_status": {
                "cpu_percent": {
                    "value": 42.0,
                    "unit": "percent",
                    "status": "available",
                    "reason": None,
                    "last_seen_at": "2026-01-01T00:00:00+00:00",
                }
            },
            "collection_strategy": "partial_fallback",
        }
    )

    lines = host_metrics_file().read_text(encoding="utf-8").splitlines()
    latest = json.loads(lines[-1])
    assert latest["metrics"]["cpu_percent"] == 42.0
    assert latest["metric_status"]["cpu_percent"]["status"] == "available"
    assert latest["collection_strategy"] == "partial_fallback"
