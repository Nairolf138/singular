"""Autonomy metrics computed from run records."""

from __future__ import annotations

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
    normalized = value
    if value.endswith("Z"):
        normalized = value[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _is_action_record(record: dict[str, Any]) -> bool:
    event = record.get("event")
    if event in {"mutation", "interaction", "refuse", "delay", "test_coevolution"}:
        return True
    return any(key in record for key in ("op", "operator", "score_new"))


def _is_proactive_record(record: dict[str, Any]) -> bool:
    proactive = record.get("proactive")
    if isinstance(proactive, bool):
        return proactive
    event = record.get("event")
    return event in {"mutation", "interaction", "test_coevolution"} or "score_new" in record


def compute_autonomy_metrics(records: list[dict[str, Any]]) -> dict[str, float | dict[str, float] | None]:
    """Compute autonomy-oriented metrics from run records."""

    action_records = [record for record in records if _is_action_record(record)]
    proactive_records = [record for record in action_records if _is_proactive_record(record)]
    proactive_rate = (
        len(proactive_records) / len(action_records) if action_records else None
    )

    health_scores = [
        score
        for record in records
        for health in [record.get("health")]
        if isinstance(health, dict)
        for score in [_as_float(health.get("score"))]
        if score is not None
    ]
    score_series = [
        score
        for record in records
        for score in [_as_float(record.get("score_new"))]
        if score is not None
    ]
    reference = score_series if score_series else health_scores
    long_term_stability = None
    if len(reference) >= 2:
        deltas = [abs(reference[idx] - reference[idx - 1]) for idx in range(1, len(reference))]
        avg_delta = mean(deltas) if deltas else 0.0
        long_term_stability = max(0.0, min(1.0, 1.0 - (avg_delta / 10.0)))

    accepted = 0
    regressive = 0
    decisions = 0
    positive_gain = 0
    total_gain = 0.0
    for record in action_records:
        accepted_value = record.get("accepted")
        if not isinstance(accepted_value, bool):
            accepted_value = record.get("ok")

        score_base = _as_float(record.get("score_base"))
        score_new = _as_float(record.get("score_new"))
        gain = None
        if score_base is not None and score_new is not None:
            gain = score_base - score_new
            total_gain += gain
            if gain > 0:
                positive_gain += 1

        if isinstance(accepted_value, bool):
            decisions += 1
            if accepted_value:
                accepted += 1
            if gain is not None and gain < 0:
                regressive += 1

    acceptance_rate = accepted / decisions if decisions else None
    regression_rate = regressive / decisions if decisions else None

    latencies_ms: list[float] = []
    last_perception_ts: datetime | None = None
    for record in records:
        if record.get("event") == "consciousness":
            parsed = _parse_ts(record.get("ts"))
            if parsed is not None:
                last_perception_ts = parsed
            continue

        direct_latency = _as_float(record.get("perception_to_action_ms"))
        if direct_latency is not None:
            latencies_ms.append(direct_latency)
            continue

        if _is_action_record(record) and last_perception_ts is not None:
            action_ts = _parse_ts(record.get("ts"))
            if action_ts is not None:
                delta_ms = (action_ts - last_perception_ts).total_seconds() * 1000.0
                if delta_ms >= 0:
                    latencies_ms.append(delta_ms)
                    continue

        runtime_latency = _as_float(record.get("ms_new"))
        if runtime_latency is not None and _is_action_record(record):
            latencies_ms.append(runtime_latency)

    perception_to_action_latency_ms = mean(latencies_ms) if latencies_ms else None

    resource_costs: list[float] = []
    total_positive_gain = 0.0
    for record in action_records:
        cost = _as_float(record.get("resource_cost"))
        if cost is None:
            metrics = record.get("mutation_metrics")
            if isinstance(metrics, dict):
                cost = _as_float(metrics.get("resource_cost"))
        if cost is None:
            cost = _as_float(record.get("ms_new"))
        if cost is not None:
            resource_costs.append(cost)

        score_base = _as_float(record.get("score_base"))
        score_new = _as_float(record.get("score_new"))
        if score_base is not None and score_new is not None and score_base > score_new:
            total_positive_gain += score_base - score_new

    resource_cost_per_gain = None
    if resource_costs and total_positive_gain > 0:
        resource_cost_per_gain = sum(resource_costs) / total_positive_gain

    return {
        "proactive_initiative_rate": proactive_rate,
        "long_term_stability": long_term_stability,
        "decision_quality": {
            "acceptance_rate": acceptance_rate,
            "regression_rate": regression_rate,
            "improvement_hit_rate": (
                positive_gain / len(action_records) if action_records else None
            ),
        },
        "perception_to_action_latency_ms": perception_to_action_latency_ms,
        "resource_cost_per_gain": resource_cost_per_gain,
        "mean_score_gain": (total_gain / len(action_records) if action_records else None),
    }
