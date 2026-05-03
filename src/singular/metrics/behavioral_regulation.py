"""Behavioral regulation metrics for orchestration and cockpit dashboards."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from statistics import mean
from typing import Any


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _parse_ts(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def compute_behavioral_regulation_metrics(
    records: list[dict[str, Any]],
    *,
    decision_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    actions = [r for r in records if str(r.get("event", "")).strip() in {"mutation", "interaction", "refuse", "delay", "test_coevolution"}]
    event_counts = Counter(str(r.get("event", "unknown")) for r in actions)
    total_actions = sum(event_counts.values())
    diversity = min(1.0, len([k for k,v in event_counts.items() if v>0]) / 5.0) if total_actions else None

    accepted = 0
    rejected = 0
    for r in actions:
        status = r.get("accepted")
        if not isinstance(status, bool):
            status = r.get("ok")
        if status is True:
            accepted += 1
        elif status is False:
            rejected += 1
    robustness = (accepted / (accepted + rejected)) if (accepted + rejected) else None

    recovery_times: list[float] = []
    last_failure: datetime | None = None
    for r in records:
        ts = _parse_ts(r.get("ts"))
        if ts is None:
            continue
        status = r.get("accepted")
        if not isinstance(status, bool):
            status = r.get("ok")
        if status is False:
            last_failure = ts
        elif status is True and last_failure is not None:
            recovery_times.append(max(0.0, (ts - last_failure).total_seconds()))
            last_failure = None
    recovery_seconds = mean(recovery_times) if recovery_times else None

    proactive = sum(1 for r in actions if r.get("proactive") is True)
    goals_autonomy = (proactive / total_actions) if total_actions else None

    health_scores = [
        _as_float((r.get("health") or {}).get("score"))
        for r in records if isinstance(r.get("health"), dict)
    ]
    health_scores = [s for s in health_scores if s is not None]
    homeo = None
    if len(health_scores) >= 2:
        volatility = mean(abs(health_scores[i]-health_scores[i-1]) for i in range(1, len(health_scores)))
        homeo = max(0.0, min(1.0, 1.0 - (volatility / 10.0)))

    trend = "stable"
    if len(health_scores) >= 4:
        half = len(health_scores)//2
        first = mean(health_scores[:half])
        second = mean(health_scores[half:])
        if second > first + 0.2:
            trend = "amélioration"
        elif second < first - 0.2:
            trend = "dégradation"

    decisions = decision_events or []
    decision_correlation = {
        "major_decisions_count": len(decisions),
        "recent_decisions": decisions[-5:],
    }

    return {
        "behavioral_diversity": diversity,
        "perturbation_robustness": robustness,
        "recovery_time_seconds": recovery_seconds,
        "goal_generation_autonomy": goals_autonomy,
        "homeostatic_stability": homeo,
        "temporal_trend": trend,
        "alerts": {
            "diversity_low": diversity is not None and diversity < 0.35,
            "robustness_low": robustness is not None and robustness < 0.55,
            "recovery_slow": recovery_seconds is not None and recovery_seconds > 120.0,
            "homeostasis_unstable": homeo is not None and homeo < 0.5,
        },
        "decision_correlation": decision_correlation,
    }


def compute_regulation_inputs(metrics: dict[str, Any]) -> dict[str, float]:
    diversity = _as_float(metrics.get("behavioral_diversity")) or 0.5
    robustness = _as_float(metrics.get("perturbation_robustness")) or 0.5
    recovery = _as_float(metrics.get("recovery_time_seconds")) or 60.0
    homeo = _as_float(metrics.get("homeostatic_stability")) or 0.5
    autonomy = _as_float(metrics.get("goal_generation_autonomy")) or 0.5

    mutation_rate_scale = max(0.6, min(1.5, 1.2 - homeo * 0.4 + (0.5 - robustness) * 0.6))
    metabolic_pressure_scale = max(0.7, min(1.6, 1.0 + (recovery / 300.0) + (0.5 - homeo) * 0.5))
    exploration_intensity_scale = max(0.5, min(1.7, 1.0 + (0.5 - diversity) * 0.8 + (autonomy - 0.5) * 0.6))

    return {
        "mutation_rate_scale": mutation_rate_scale,
        "metabolic_pressure_scale": metabolic_pressure_scale,
        "exploration_intensity_scale": exploration_intensity_scale,
    }
