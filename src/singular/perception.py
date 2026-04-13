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

from singular.events import EventBus, get_global_event_bus


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
) -> dict[str, Any]:
    """Collect sensory signals and optionally publish perception events."""
    signals: dict[str, Any] = {
        "temperature": random.uniform(-20.0, 40.0),
        "is_daytime": 6 <= time.localtime().tm_hour < 18,
        "noise": random.random(),
    }
    signals.update(_read_optional_file())
    signals.update(_query_optional_weather_api())

    root = _resolve_sandbox_root(sandbox_root)
    state = artifact_state or _ARTIFACT_STATE
    filter_instance = noise_filter or _NOISE_FILTER
    artifact_events = _collect_artifact_signals(root, state)
    filtered_events = [event for event in artifact_events if filter_instance.allow(event)]
    if filtered_events:
        signals["artifact_events"] = filtered_events

    if publish_event:
        emitter = bus or get_global_event_bus()
        emitter.publish("signal.captured", {"signals": dict(signals)}, payload_version=1)
        for event in filtered_events:
            emitter.publish(
                "artifact.perception",
                {"version": "1.0", "event": event},
                payload_version=1,
            )
    return signals
