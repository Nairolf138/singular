"""Semantic event derivation from raw OS snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .capture import OSSnapshot


@dataclass(frozen=True)
class SemanticRuleConfig:
    """Thresholds and keyword rules for semantic transformation."""

    meeting_keywords: tuple[str, ...] = ("meet", "zoom", "teams", "calendar")
    coding_keywords: tuple[str, ...] = ("code", "pycharm", "vscode", "terminal", "vim")
    high_cpu_threshold: float = 85.0
    low_battery_threshold: float = 20.0


class OSSemanticInterpreter:
    """Derive human-meaningful context events from OS snapshots."""

    def __init__(self, config: SemanticRuleConfig | None = None) -> None:
        self.config = config or SemanticRuleConfig()

    def derive(self, snapshot: OSSnapshot) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []

        app = snapshot.active_window.app.lower()
        title = snapshot.active_window.title.lower()
        joined = f"{app} {title}"

        if any(keyword in joined for keyword in self.config.meeting_keywords):
            events.append(
                {
                    "type": "user.in_meeting",
                    "confidence": 0.86,
                    "reason": "active_window_keywords",
                    "window": snapshot.active_window.title,
                    "application": snapshot.active_window.app,
                }
            )

        if any(keyword in joined for keyword in self.config.coding_keywords):
            events.append(
                {
                    "type": "workspace.coding_active",
                    "confidence": 0.82,
                    "reason": "active_window_keywords",
                    "window": snapshot.active_window.title,
                    "application": snapshot.active_window.app,
                }
            )

        cpu = snapshot.host_state.cpu_percent
        if isinstance(cpu, (int, float)) and float(cpu) >= self.config.high_cpu_threshold:
            events.append(
                {
                    "type": "host.cpu_high",
                    "confidence": 0.9,
                    "reason": "cpu_threshold",
                    "cpu_percent": float(cpu),
                    "threshold": self.config.high_cpu_threshold,
                }
            )

        battery = snapshot.host_state.battery_percent
        charging = snapshot.host_state.battery_charging
        if (
            isinstance(battery, (int, float))
            and float(battery) <= self.config.low_battery_threshold
            and charging is False
        ):
            events.append(
                {
                    "type": "host.battery_low",
                    "confidence": 0.92,
                    "reason": "battery_threshold",
                    "battery_percent": float(battery),
                    "charging": bool(charging),
                    "threshold": self.config.low_battery_threshold,
                }
            )

        if any("calendar" in n.app.lower() for n in snapshot.notifications):
            events.append(
                {
                    "type": "user.calendar_prompt",
                    "confidence": 0.74,
                    "reason": "notification_source",
                    "count": sum(
                        1
                        for n in snapshot.notifications
                        if "calendar" in n.app.lower()
                    ),
                }
            )

        return events
