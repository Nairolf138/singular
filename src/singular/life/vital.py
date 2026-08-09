"""Deterministic, auditable vital-state rules.

The lifecycle is deliberately monotonic once death has been confirmed.  Recovery
is possible before ``terminal``; leaving ``terminal`` requires restoring a known
healthy checkpoint rather than merely observing a better activity score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Iterable


class VitalState(StrEnum):
    STABLE = "stable"
    AT_RISK = "at_risk"
    CRITICAL = "critical"
    TERMINAL = "terminal"
    DEAD = "dead"
    EXTINCT = "extinct"


ALLOWED_TRANSITIONS: dict[VitalState, frozenset[VitalState]] = {
    VitalState.STABLE: frozenset({VitalState.AT_RISK}),
    VitalState.AT_RISK: frozenset({VitalState.STABLE, VitalState.CRITICAL}),
    VitalState.CRITICAL: frozenset({VitalState.AT_RISK, VitalState.TERMINAL}),
    VitalState.TERMINAL: frozenset({VitalState.CRITICAL, VitalState.DEAD}),
    VitalState.DEAD: frozenset({VitalState.EXTINCT}),
    VitalState.EXTINCT: frozenset(),
}


@dataclass(frozen=True)
class VitalThresholds:
    decline_age: int = 50
    terminal_age: int = 120
    critical_health: float = 40.0
    terminal_health: float = 25.0
    high_failure_rate: float = 0.6
    terminal_failure_streak: int = 5
    reproduction_min_age: int = 3
    reproduction_max_age: int = 80
    extinction_min_signals: int = 2
    extinction_min_duration: int = 3


@dataclass
class VitalStateMachine:
    """Validate transitions and retain the evidence behind irreversible ones."""

    state: VitalState = VitalState.STABLE
    root_cause: str | None = None
    rescue_attempts: list[str] = field(default_factory=list)
    last_irreversible_decision: str | None = None

    def transition(
        self, target: VitalState | str, *, cause: str, checkpoint_restored: bool = False
    ) -> VitalState:
        target = VitalState(target)
        if target == self.state:
            return self.state
        if target not in ALLOWED_TRANSITIONS[self.state]:
            raise ValueError(
                f"forbidden vital transition: {self.state.value}->{target.value}"
            )
        if (
            self.state is VitalState.TERMINAL
            and target is VitalState.CRITICAL
            and not checkpoint_restored
        ):
            raise ValueError("terminal recovery requires a healthy checkpoint")
        self.root_cause = self.root_cause or cause
        if target in {VitalState.DEAD, VitalState.EXTINCT}:
            self.last_irreversible_decision = (
                f"{self.state.value}->{target.value}:{cause}"
            )
        self.state = target
        return target

    def record_rescue(self, attempt: str) -> None:
        self.rescue_attempts.append(attempt)

    def audit(self) -> dict[str, object]:
        return {
            "root_cause": self.root_cause,
            "rescue_attempts": list(self.rescue_attempts),
            "last_irreversible_decision": self.last_irreversible_decision,
        }


def compute_vital_timeline(
    *,
    age: int,
    current_health: float | None,
    failure_rate: float | None,
    failure_streak: int,
    extinction_seen: bool,
    registry_status: str | None = None,
    extinction_signals: Iterable[str] = (),
    extinction_duration: int = 0,
    root_cause: str | None = None,
    rescue_attempts: Iterable[str] = (),
    last_irreversible_decision: str | None = None,
    thresholds: VitalThresholds = VitalThresholds(),
) -> dict[str, object]:
    """Classify a snapshot; extinction needs concordant, sustained evidence."""

    causes: list[str] = []
    signals = set(extinction_signals)
    if extinction_seen:
        signals.add("extinction_event")
    if registry_status == "extinct":
        signals.add("registry_extinct")
    extinction_confirmed = (
        len(signals) >= thresholds.extinction_min_signals
        and extinction_duration >= thresholds.extinction_min_duration
    )
    if extinction_confirmed:
        state = VitalState.EXTINCT
        causes.append("sustained_concordant_extinction_evidence")
    elif registry_status == "dead":
        state = VitalState.DEAD
        causes.append("death_recorded")
    elif (
        age >= thresholds.terminal_age
        or failure_streak >= thresholds.terminal_failure_streak
    ):
        state = VitalState.TERMINAL
        causes.append(
            "terminal_age_reached"
            if age >= thresholds.terminal_age
            else "failure_streak"
        )
    elif current_health is not None and current_health <= thresholds.terminal_health:
        state = VitalState.TERMINAL
        causes.append("critical_health_score")
    elif (
        current_health is not None and current_health <= thresholds.critical_health
    ) or (failure_rate is not None and failure_rate >= thresholds.high_failure_rate):
        state = VitalState.CRITICAL
        causes.append(
            "critical_health_score"
            if current_health is not None
            and current_health <= thresholds.critical_health
            else "high_failure_rate"
        )
    elif age >= thresholds.decline_age:
        state = VitalState.AT_RISK
        causes.append("age_decline_threshold")
    else:
        state = VitalState.STABLE

    reproduction_eligible = (
        state in {VitalState.STABLE, VitalState.AT_RISK}
        and thresholds.reproduction_min_age <= age <= thresholds.reproduction_max_age
    )
    return {
        "age": age,
        "current_failure_streak": failure_streak,
        "state": state.value,
        "risk_level": (
            "high"
            if state
            in {
                VitalState.CRITICAL,
                VitalState.TERMINAL,
                VitalState.DEAD,
                VitalState.EXTINCT,
            }
            else ("medium" if state is VitalState.AT_RISK else "low")
        ),
        "terminal": state in {VitalState.TERMINAL, VitalState.DEAD, VitalState.EXTINCT},
        "causes": causes,
        "reproduction_eligible": reproduction_eligible,
        "extinction_evidence": {
            "signals": sorted(signals),
            "duration": extinction_duration,
            "confirmed": extinction_confirmed,
            "required_signals": thresholds.extinction_min_signals,
            "required_duration": thresholds.extinction_min_duration,
        },
        "audit": {
            "root_cause": root_cause or (causes[0] if causes else None),
            "rescue_attempts": list(rescue_attempts),
            "last_irreversible_decision": last_irreversible_decision,
        },
        "thresholds": {
            "decline_age": thresholds.decline_age,
            "terminal_age": thresholds.terminal_age,
            "critical_health": thresholds.critical_health,
            "terminal_health": thresholds.terminal_health,
            "high_failure_rate": thresholds.high_failure_rate,
            "terminal_failure_streak": thresholds.terminal_failure_streak,
            "reproduction_age_window": [
                thresholds.reproduction_min_age,
                thresholds.reproduction_max_age,
            ],
        },
    }
