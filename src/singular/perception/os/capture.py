"""OS-level signal capture (best effort, privacy preserving)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol


@dataclass(frozen=True)
class NotificationRecord:
    """Compact system notification record."""

    app: str
    title: str
    body_preview: str
    observed_at: str
    priority: str = "normal"


@dataclass(frozen=True)
class ActiveWindowState:
    """Foreground window metadata."""

    app: str
    title: str


@dataclass(frozen=True)
class InputState:
    """Privacy-preserving user input state."""

    mouse_x: int | None
    mouse_y: int | None
    keyboard_active: bool
    idle_seconds: float


@dataclass(frozen=True)
class HostState:
    """Host operating state summary."""

    network_online: bool | None
    network_type: str | None
    battery_percent: float | None
    battery_charging: bool | None
    cpu_percent: float | None


@dataclass(frozen=True)
class OSSnapshot:
    """Aggregated snapshot from OS sensors."""

    observed_at: str
    active_window: ActiveWindowState
    input_state: InputState
    notifications: list[NotificationRecord] = field(default_factory=list)
    host_state: HostState = field(
        default_factory=lambda: HostState(
            network_online=None,
            network_type=None,
            battery_percent=None,
            battery_charging=None,
            cpu_percent=None,
        )
    )

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


class OSSnapshotProvider(Protocol):
    """Contract for OS snapshot providers."""

    def collect_snapshot(self) -> OSSnapshot:
        """Collect one OS snapshot."""


class BestEffortOSSnapshotProvider:
    """Portable provider that captures what is available without keylogging."""

    source_name = "os.capture"

    def __init__(self) -> None:
        self._last_notifications: set[tuple[str, str, str]] = set()

    def collect_snapshot(self) -> OSSnapshot:
        observed_at = datetime.now(timezone.utc).isoformat()
        return OSSnapshot(
            observed_at=observed_at,
            active_window=self._collect_active_window(),
            input_state=self._collect_input_state(),
            notifications=self._collect_notifications(observed_at=observed_at),
            host_state=self._collect_host_state(),
        )

    def _collect_active_window(self) -> ActiveWindowState:
        # Best-effort placeholders: real platform hooks can override this provider.
        return ActiveWindowState(app="unknown", title="unknown")

    def _collect_input_state(self) -> InputState:
        mouse_x: int | None = None
        mouse_y: int | None = None
        try:
            import pyautogui  # type: ignore[import-untyped]

            point = pyautogui.position()
            mouse_x, mouse_y = int(point.x), int(point.y)
        except Exception:
            pass

        return InputState(
            mouse_x=mouse_x,
            mouse_y=mouse_y,
            keyboard_active=False,
            idle_seconds=0.0,
        )

    def _collect_notifications(self, *, observed_at: str) -> list[NotificationRecord]:
        # No default OS backend to avoid hard deps. Integrators can subclass.
        _ = observed_at
        return []

    def _collect_host_state(self) -> HostState:
        cpu_percent: float | None = None
        battery_percent: float | None = None
        battery_charging: bool | None = None
        network_online: bool | None = None
        network_type: str | None = None

        try:
            import psutil  # type: ignore[import-untyped]

            cpu_percent = float(psutil.cpu_percent(interval=0.0))
            battery = psutil.sensors_battery()
            if battery is not None:
                battery_percent = float(battery.percent)
                battery_charging = bool(battery.power_plugged)

            interfaces = psutil.net_if_stats()
            online = [name for name, stats in interfaces.items() if stats.isup]
            network_online = bool(online)
            if online:
                lowered = {name.lower() for name in online}
                if any("wi" in name or "wlan" in name for name in lowered):
                    network_type = "wifi"
                elif any("eth" in name or "en" in name for name in lowered):
                    network_type = "ethernet"
                else:
                    network_type = "unknown"
        except Exception:
            pass

        return HostState(
            network_online=network_online,
            network_type=network_type,
            battery_percent=battery_percent,
            battery_charging=battery_charging,
            cpu_percent=cpu_percent,
        )
