"""Periodic reevaluation of an agent's goals."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Iterable

from singular.agents import Agent
from singular.environment import notifications


def reevaluate_goals(agent: Agent) -> None:
    """Trigger the agent to reconsider its current goal."""

    agent.choose_goal()


@dataclass(frozen=True)
class Alert:
    """Alert emitted when reevaluation thresholds are exceeded."""

    kind: str
    level: notifications.Level
    message: str
    action: str

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "level": self.level,
            "message": self.message,
            "action": self.action,
        }


def detect_alerts(
    *,
    health_scores: Iterable[float],
    sandbox_failure_rates: Iterable[float],
    stagnation_steps: int,
    decline_window: int = 5,
    sandbox_window: int = 5,
    stagnation_threshold: int = 12,
) -> list[Alert]:
    """Detect alerts for health decline, sandbox failures and stagnation."""

    alerts: list[Alert] = []
    health = [float(score) for score in health_scores]
    sandbox = [float(rate) for rate in sandbox_failure_rates]

    if len(health) >= decline_window:
        window = health[-decline_window:]
        if all(curr < prev for prev, curr in zip(window, window[1:])):
            alerts.append(
                Alert(
                    kind="health_decline",
                    level="warning",
                    message="baisse continue du health score",
                    action="réduire exploration",
                )
            )

    if len(sandbox) >= sandbox_window * 2:
        previous = sandbox[-(sandbox_window * 2) : -sandbox_window]
        recent = sandbox[-sandbox_window:]
        previous_avg = sum(previous) / len(previous)
        recent_avg = sum(recent) / len(recent)
        if recent_avg - previous_avg >= 0.15 and recent_avg >= 0.25:
            alerts.append(
                Alert(
                    kind="sandbox_failures_rising",
                    level="critical",
                    message="hausse des échecs sandbox",
                    action="changer opérateurs",
                )
            )

    if stagnation_steps >= stagnation_threshold:
        alerts.append(
            Alert(
                kind="prolonged_stagnation",
                level="warning",
                message="stagnation prolongée détectée",
                action="réduire exploration",
            )
        )
    return alerts


def alerts_from_records(
    records: Iterable[dict[str, object]],
    *,
    decline_window: int = 5,
    sandbox_window: int = 5,
    stagnation_threshold: int = 12,
) -> list[dict[str, str]]:
    """Build alerts from run log records."""

    health_scores: list[float] = []
    sandbox_failure_rates: list[float] = []
    stagnation_steps = 0
    for record in records:
        health = record.get("health")
        if isinstance(health, dict):
            if isinstance(health.get("score"), (int, float)):
                health_scores.append(float(health["score"]))
            stability = health.get("sandbox_stability")
            if isinstance(stability, (int, float)):
                sandbox_failure_rates.append(1.0 - float(stability))

        accepted = record.get("accepted")
        if isinstance(accepted, bool):
            stagnation_steps = 0 if accepted else stagnation_steps + 1

    return [
        alert.to_dict()
        for alert in detect_alerts(
            health_scores=health_scores,
            sandbox_failure_rates=sandbox_failure_rates,
            stagnation_steps=stagnation_steps,
            decline_window=decline_window,
            sandbox_window=sandbox_window,
            stagnation_threshold=stagnation_threshold,
        )
    ]


def start(interval: float, agent: Agent) -> threading.Event:
    """Start a background scheduler calling ``reevaluate_goals``.

    The scheduler reevaluates ``agent``'s goals every ``interval`` seconds.
    A :class:`threading.Event` is returned which can be set to stop the
    scheduler.
    """

    stop_event = threading.Event()

    def loop() -> None:
        while not stop_event.is_set():
            reevaluate_goals(agent)
            if hasattr(agent, "alerts") and isinstance(agent.alerts, list):
                for alert in agent.alerts:
                    if isinstance(alert, dict):
                        level = str(alert.get("level", "info"))
                        if level in {"info", "warning", "critical"}:
                            notifications.notify(
                                str(alert.get("message", "")),
                                level=level,
                                action=str(alert.get("action", "")),
                            )
            time.sleep(interval)

    threading.Thread(target=loop, daemon=True).start()
    return stop_event


__all__ = ["Alert", "alerts_from_records", "detect_alerts", "reevaluate_goals", "start"]
