from __future__ import annotations

from singular.metrics.autonomy import compute_autonomy_metrics


def test_compute_autonomy_metrics_core_indicators() -> None:
    records = [
        {
            "ts": "2026-04-12T10:00:00",
            "event": "consciousness",
        },
        {
            "ts": "2026-04-12T10:00:01",
            "event": "mutation",
            "accepted": True,
            "score_base": 10.0,
            "score_new": 8.0,
            "resource_cost": 2.0,
        },
        {
            "ts": "2026-04-12T10:00:03",
            "event": "mutation",
            "accepted": False,
            "score_base": 8.0,
            "score_new": 9.0,
            "resource_cost": 1.0,
        },
        {
            "ts": "2026-04-12T10:00:05",
            "event": "delay",
            "ms_new": 4.0,
        },
    ]

    metrics = compute_autonomy_metrics(records)

    assert metrics["proactive_initiative_rate"] == 2 / 3
    assert isinstance(metrics["long_term_stability"], float)
    assert metrics["perception_to_action_latency_ms"] == 3000.0
    assert metrics["resource_cost_per_gain"] == 3.5

    quality = metrics["decision_quality"]
    assert isinstance(quality, dict)
    assert quality["acceptance_rate"] == 0.5
    assert quality["regression_rate"] == 0.5
