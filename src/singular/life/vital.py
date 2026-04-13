"""Deterministic and observable vital-state rules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VitalThresholds:
    decline_age: int = 50
    terminal_age: int = 120
    terminal_health: float = 25.0
    high_failure_rate: float = 0.6
    terminal_failure_streak: int = 5
    reproduction_min_age: int = 3
    reproduction_max_age: int = 80


def compute_vital_timeline(
    *,
    age: int,
    current_health: float | None,
    failure_rate: float | None,
    failure_streak: int,
    extinction_seen: bool,
    registry_status: str | None = None,
    thresholds: VitalThresholds = VitalThresholds(),
) -> dict[str, object]:
    """Return an observable timeline payload from deterministic rules."""

    causes: list[str] = []
    if extinction_seen or registry_status == "extinct":
        state = "extinct"
        causes.append("extinction_observed")
    else:
        state = "mature"
        if age >= thresholds.decline_age:
            state = "declining"
            causes.append("age_decline_threshold")
        if failure_rate is not None and failure_rate >= thresholds.high_failure_rate:
            state = "declining"
            causes.append("high_failure_rate")
        if age >= thresholds.terminal_age:
            state = "terminal"
            causes.append("terminal_age_reached")
        if (
            current_health is not None
            and current_health <= thresholds.terminal_health
        ):
            state = "terminal"
            causes.append("critical_health_score")
        if failure_streak >= thresholds.terminal_failure_streak:
            state = "terminal"
            causes.append("failure_streak")

    risk_level = "low"
    if state in {"declining"}:
        risk_level = "medium"
    if state in {"terminal", "extinct"}:
        risk_level = "high"

    reproduction_eligible = (
        state in {"mature", "declining"}
        and thresholds.reproduction_min_age <= age <= thresholds.reproduction_max_age
        and (failure_rate is None or failure_rate < thresholds.high_failure_rate)
        and (current_health is None or current_health > thresholds.terminal_health)
    )

    return {
        "age": age,
        "state": state,
        "risk_level": risk_level,
        "terminal": state in {"terminal", "extinct"},
        "causes": causes,
        "reproduction_eligible": reproduction_eligible,
        "thresholds": {
            "decline_age": thresholds.decline_age,
            "terminal_age": thresholds.terminal_age,
            "terminal_health": thresholds.terminal_health,
            "high_failure_rate": thresholds.high_failure_rate,
            "terminal_failure_streak": thresholds.terminal_failure_streak,
            "reproduction_age_window": [
                thresholds.reproduction_min_age,
                thresholds.reproduction_max_age,
            ],
        },
    }

