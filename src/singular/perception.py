"""Perception utilities.

This module provides a :func:`capture_signals` function that gathers basic
sensory inputs.  It includes a few virtual sensors (temperature, a simple
cycle to indicate day or night, and ambient noise).  Optional connectors can
supply real-world data by reading from a file or querying a weather API.

The module also exposes sandboxed ``artifact.*`` sensors that inspect local
project state (modified files, new logs and simple technical debt markers) and
publishes normalized perception events on the :class:`~singular.events.EventBus`.
"""

from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from singular.environment.sim_world import load_world_state
from singular.events import EventBus, get_global_event_bus
from singular.governance.policy import MutationGovernancePolicy
from singular.sensors import (
    append_host_metrics_sample,
    collect_host_metrics,
    compute_host_metrics_aggregates,
    load_host_sensor_thresholds,
)


def _read_optional_file() -> dict[str, Any]:
    """Read data from ``SINGULAR_SENSOR_FILE`` if available."""
    path = os.getenv("SINGULAR_SENSOR_FILE")
    if not path:
        return {}
    try:
        return {"file": Path(path).read_text(encoding="utf-8").strip()}
    except Exception:
        return {}


def _query_optional_weather_api() -> dict[str, Any]:
    """Query ``SINGULAR_WEATHER_API`` for weather data if possible."""
    url = os.getenv("SINGULAR_WEATHER_API")
    if not url:
        return {}
    try:  # pragma: no cover - network failures are expected
        import requests  # type: ignore[import-untyped]

        timeout_str = os.getenv("SINGULAR_HTTP_TIMEOUT", "5")
        try:
            timeout = float(timeout_str)
        except ValueError:
            timeout = 5.0
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return {"weather": response.json()}
    except Exception:
        return {}


def _resolve_sandbox_root(path: str | Path | None) -> Path:
    if path is None:
        path = os.getenv("SINGULAR_SANDBOX_ROOT", "sandbox")
    candidate = Path(path).resolve()
    if not candidate.exists() or not candidate.is_dir():
        return candidate
    return candidate


def _list_sandbox_files(root: Path) -> dict[str, float]:
    if not root.exists() or not root.is_dir():
        return {}
    files: dict[str, float] = {}
    for p in root.rglob("*"):
        if p.is_file():
            files[str(p.relative_to(root))] = p.stat().st_mtime
    return files


def _count_tech_debt(root: Path) -> int:
    if not root.exists() or not root.is_dir():
        return 0
    markers = ("TODO", "FIXME", "HACK")
    total = 0
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in {".py", ".md", ".txt", ".yml", ".yaml", ".json"}:
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        upper = content.upper()
        for marker in markers:
            total += upper.count(marker)
    return total


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class _ArtifactScanState:
    files_mtime: dict[str, float] = field(default_factory=dict)
    seen_logs: set[str] = field(default_factory=set)


@dataclass
class PerceptionNoiseFilter:
    """Simple anti-noise filter using confidence, dedupe and cooldown."""

    confidence_threshold: float = 0.45
    cooldown_seconds: float = 5.0
    deduplicate: bool = True
    _seen_signatures: set[str] = field(default_factory=set)
    _last_emitted_at: dict[str, float] = field(default_factory=dict)

    def allow(self, event: dict[str, Any]) -> bool:
        confidence = float(event.get("confidence", 0.0))
        if confidence < self.confidence_threshold:
            return False

        event_type = str(event.get("type", ""))
        now = time.monotonic()
        last_at = self._last_emitted_at.get(event_type)
        if last_at is not None and (now - last_at) < self.cooldown_seconds:
            return False

        signature = str((event_type, event.get("source"), event.get("data")))
        if self.deduplicate and signature in self._seen_signatures:
            return False

        self._last_emitted_at[event_type] = now
        self._seen_signatures.add(signature)
        return True


_ARTIFACT_STATE = _ArtifactScanState()
_NOISE_FILTER = PerceptionNoiseFilter()


def _build_perception_event(
    *,
    event_type: str,
    source: str,
    confidence: float,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Normalized perception event format."""

    return {
        "type": event_type,
        "source": source,
        "confidence": max(0.0, min(1.0, confidence)),
        "timestamp": _iso_now(),
        "data": data,
    }




def _collect_host_signals() -> dict[str, float | None] | None:
    """Collect host metrics in a backward-compatible best-effort mode."""

    try:
        policy = MutationGovernancePolicy()
        if not policy.allow_sensor("host_metrics"):
            return None
        metrics = collect_host_metrics()
        opt_in = os.getenv("SINGULAR_SENSOR_SENSITIVE_OPT_IN", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        sanitized = policy.sanitize_sensor_metrics(
            sensor_name="host_metrics",
            metrics=metrics,
            requested_granularity="detailed",
            explicit_sensitive_opt_in=opt_in,
        )
        return sanitized or None
    except Exception:
        return None


def _derive_host_events(host_metrics: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Emit normalized host events when predefined thresholds are exceeded."""

    if not isinstance(host_metrics, dict):
        return []

    thresholds = load_host_sensor_thresholds()
    events: list[dict[str, Any]] = []

    cpu_percent = host_metrics.get("cpu_percent")
    if isinstance(cpu_percent, (int, float)) and float(cpu_percent) >= thresholds.cpu_critical_percent:
        events.append(
            _build_perception_event(
                event_type="host.cpu.critical",
                source="host_metrics",
                confidence=0.95,
                data={
                    "cpu_percent": float(cpu_percent),
                    "severity": "critical",
                    "threshold": thresholds.cpu_critical_percent,
                },
            )
        )
    elif isinstance(cpu_percent, (int, float)) and float(cpu_percent) >= thresholds.cpu_warning_percent:
        events.append(
            _build_perception_event(
                event_type="host.cpu.warning",
                source="host_metrics",
                confidence=0.9,
                data={
                    "cpu_percent": float(cpu_percent),
                    "severity": "warning",
                    "threshold": thresholds.cpu_warning_percent,
                },
            )
        )

    ram_used_percent = host_metrics.get("ram_used_percent")
    if isinstance(ram_used_percent, (int, float)) and float(ram_used_percent) >= thresholds.ram_critical_percent:
        events.append(
            _build_perception_event(
                event_type="host.memory.critical",
                source="host_metrics",
                confidence=0.94,
                data={
                    "ram_used_percent": float(ram_used_percent),
                    "severity": "critical",
                    "threshold": thresholds.ram_critical_percent,
                },
            )
        )
    elif isinstance(ram_used_percent, (int, float)) and float(ram_used_percent) >= thresholds.ram_warning_percent:
        events.append(
            _build_perception_event(
                event_type="host.memory.warning",
                source="host_metrics",
                confidence=0.89,
                data={
                    "ram_used_percent": float(ram_used_percent),
                    "severity": "warning",
                    "threshold": thresholds.ram_warning_percent,
                },
            )
        )

    host_temperature_c = host_metrics.get("host_temperature_c")
    if (
        isinstance(host_temperature_c, (int, float))
        and float(host_temperature_c) >= thresholds.temperature_critical_c
    ):
        events.append(
            _build_perception_event(
                event_type="host.thermal.critical",
                source="host_metrics",
                confidence=0.93,
                data={
                    "host_temperature_c": float(host_temperature_c),
                    "severity": "critical",
                    "threshold": thresholds.temperature_critical_c,
                },
            )
        )
    elif (
        isinstance(host_temperature_c, (int, float))
        and float(host_temperature_c) >= thresholds.temperature_warning_c
    ):
        events.append(
            _build_perception_event(
                event_type="host.thermal.warning",
                source="host_metrics",
                confidence=0.88,
                data={
                    "host_temperature_c": float(host_temperature_c),
                    "severity": "warning",
                    "threshold": thresholds.temperature_warning_c,
                },
            )
        )

    disk_used_percent = host_metrics.get("disk_used_percent")
    if isinstance(disk_used_percent, (int, float)) and float(disk_used_percent) >= thresholds.disk_critical_percent:
        events.append(
            _build_perception_event(
                event_type="host.disk.critical",
                source="host_metrics",
                confidence=0.91,
                data={
                    "disk_used_percent": float(disk_used_percent),
                    "severity": "critical",
                    "threshold": thresholds.disk_critical_percent,
                },
            )
        )

    return events


def _collect_artifact_signals(root: Path, state: _ArtifactScanState) -> list[dict[str, Any]]:
    files_mtime = _list_sandbox_files(root)
    previous_files = state.files_mtime

    modified_files = sorted(
        rel
        for rel, mtime in files_mtime.items()
        if rel in previous_files and previous_files[rel] != mtime
    )

    new_logs = sorted(
        rel
        for rel in files_mtime
        if rel.endswith(".log") and rel not in state.seen_logs
    )

    debt_count = _count_tech_debt(root)

    state.files_mtime = files_mtime
    state.seen_logs.update(new_logs)

    events: list[dict[str, Any]] = []
    if modified_files:
        events.append(
            _build_perception_event(
                event_type="artifact.files.modified",
                source=str(root),
                confidence=0.95,
                data={"count": len(modified_files), "files": modified_files},
            )
        )
    if new_logs:
        events.append(
            _build_perception_event(
                event_type="artifact.logs.new",
                source=str(root),
                confidence=0.9,
                data={"count": len(new_logs), "files": new_logs},
            )
        )
    events.append(
        _build_perception_event(
            event_type="artifact.tech_debt.simple",
            source=str(root),
            confidence=0.6,
            data={"markers": debt_count},
        )
    )
    return events


def _derive_world_events(world_state: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(world_state, dict):
        return []
    events: list[dict[str, Any]] = []
    health = world_state.get("global_health", {}) if isinstance(world_state.get("global_health"), dict) else {}
    trend = str(health.get("trend", "stable"))
    score = float(health.get("score", 50.0) or 50.0)
    if trend == "degrading" or score < 45.0:
        events.append(
            _build_perception_event(
                event_type="world.health.degradation",
                source="world_state",
                confidence=0.9,
                data={"trend": trend, "score": score},
            )
        )

    resources = world_state.get("resources", {}) if isinstance(world_state.get("resources"), dict) else {}
    renewable = resources.get("renewable", {}) if isinstance(resources.get("renewable"), dict) else {}
    scarcity: list[dict[str, float | str]] = []
    opportunities: list[dict[str, float | str]] = []
    for name, payload in renewable.items():
        if not isinstance(payload, dict):
            continue
        amount = float(payload.get("amount", 0.0) or 0.0)
        capacity = max(float(payload.get("capacity", 0.0) or 0.0), 0.0)
        coverage = (amount / capacity) if capacity else 0.0
        if coverage <= 0.2:
            scarcity.append({"resource": str(name), "coverage": round(coverage, 3)})
        if coverage >= 0.8:
            opportunities.append({"resource": str(name), "coverage": round(coverage, 3)})

    if scarcity:
        events.append(
            _build_perception_event(
                event_type="world.resource.scarcity",
                source="world_state",
                confidence=0.92,
                data={"resources": scarcity},
            )
        )
    if opportunities:
        events.append(
            _build_perception_event(
                event_type="world.opportunity.window",
                source="world_state",
                confidence=0.85,
                data={"resources": opportunities},
            )
        )
    return events



def reset_perception_state() -> None:
    """Reset in-memory artifact scan and anti-noise state (tests/helpers)."""

    _ARTIFACT_STATE.files_mtime.clear()
    _ARTIFACT_STATE.seen_logs.clear()
    _NOISE_FILTER._seen_signatures.clear()
    _NOISE_FILTER._last_emitted_at.clear()

def get_temperature() -> float:
    """Return the current temperature.

    A weather API can be provided via ``SINGULAR_WEATHER_API``. When present
    and a ``temp`` or ``temperature`` field is found in the returned JSON it is
    used.  Otherwise a simulated temperature is produced.
    """

    data = _query_optional_weather_api()
    weather = data.get("weather") if isinstance(data, dict) else None
    if isinstance(weather, dict):
        containers = [weather]
        main = weather.get("main")
        if isinstance(main, dict):
            containers.append(main)
        for container in containers:
            for key in ("temp", "temperature"):
                if key in container:
                    try:
                        return float(container[key])
                    except (TypeError, ValueError):
                        pass
    return random.uniform(-20.0, 40.0)


def capture_signals(
    *,
    bus: EventBus | None = None,
    publish_event: bool = True,
    sandbox_root: str | Path | None = None,
    noise_filter: PerceptionNoiseFilter | None = None,
    artifact_state: _ArtifactScanState | None = None,
    world_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Collect sensory signals and optionally publish perception events."""
    signals: dict[str, Any] = {
        "temperature": random.uniform(-20.0, 40.0),
        "is_daytime": 6 <= time.localtime().tm_hour < 18,
        "noise": random.random(),
    }
    signals.update(_read_optional_file())
    signals.update(_query_optional_weather_api())

    host_metrics = _collect_host_signals()
    if host_metrics is not None:
        signals["host_metrics"] = host_metrics
        try:
            append_host_metrics_sample(host_metrics)
            signals["host_metrics_aggregates"] = compute_host_metrics_aggregates()
        except Exception:
            pass

    root = _resolve_sandbox_root(sandbox_root)
    state = artifact_state or _ARTIFACT_STATE
    filter_instance = noise_filter or _NOISE_FILTER
    artifact_events = _collect_artifact_signals(root, state)
    host_events = _derive_host_events(host_metrics)
    resolved_world_state = world_state
    if resolved_world_state is None:
        try:
            resolved_world_state = load_world_state()
        except Exception:
            resolved_world_state = None
    world_events = _derive_world_events(resolved_world_state)
    candidate_events = [*artifact_events, *host_events, *world_events]
    filtered_events = [event for event in candidate_events if filter_instance.allow(event)]
    if filtered_events:
        signals["artifact_events"] = [
            event for event in filtered_events if str(event.get("type", "")).startswith("artifact.")
        ]
        signals["host_events"] = [
            event for event in filtered_events if str(event.get("type", "")).startswith("host.")
        ]
        if not signals["artifact_events"]:
            signals.pop("artifact_events")
        if not signals["host_events"]:
            signals.pop("host_events")
        signals["world_events"] = [
            event for event in filtered_events if str(event.get("type", "")).startswith("world.")
        ]
        if not signals["world_events"]:
            signals.pop("world_events")

    if publish_event:
        emitter = bus or get_global_event_bus()
        emitter.publish("signal.captured", {"signals": dict(signals)}, payload_version=1)
        for event in filtered_events:
            topic = (
                "artifact.perception"
                if str(event.get("type", "")).startswith("artifact.")
                else "host.perception"
                if str(event.get("type", "")).startswith("host.")
                else "world.perception"
            )
            emitter.publish(
                topic,
                {"version": "1.0", "event": event},
                payload_version=1,
            )
    return signals
