"""Watch daemon: periodic perception, change detection and event emission."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any

from ..memory import get_mem_dir
from ..perception import capture_signals


SUPPORTED_SOURCES = {"file", "weather", "runs", "folder"}


class InternalEventBus:
    """Small internal event bus used by the watch daemon."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events.append({"event_type": event_type, "payload": payload})


@dataclass
class WatchConfig:
    """Runtime configuration for the watch daemon."""

    interval_seconds: float = 5.0
    sources: set[str] | None = None
    cpu_budget_percent: float = 50.0
    memory_budget_mb: float = 512.0
    dry_run: bool = False
    watch_dir: Path | None = None


class WatchDaemon:
    """Monitor system signals, detect significant changes and emit events."""

    def __init__(
        self,
        *,
        config: WatchConfig,
        bus: InternalEventBus | None = None,
    ) -> None:
        self.config = config
        self.bus = bus or InternalEventBus()
        self.previous_snapshot: dict[str, Any] | None = None

    def _runs_snapshot(self) -> dict[str, Any]:
        base_dir = Path(os.environ.get("SINGULAR_HOME", ".")) / "runs"
        if not base_dir.exists():
            return {"count": 0, "latest_mtime": None}

        run_files = sorted(base_dir.rglob("*.jsonl"))
        latest_mtime = max((entry.stat().st_mtime for entry in run_files), default=None)
        return {"count": len(run_files), "latest_mtime": latest_mtime}

    def _folder_snapshot(self) -> dict[str, Any]:
        watch_dir = self.config.watch_dir or Path(os.environ.get("SINGULAR_HOME", "."))
        if not watch_dir.exists() or not watch_dir.is_dir():
            return {"exists": False, "count": 0, "latest_mtime": None}

        entries = [entry for entry in watch_dir.iterdir()]
        latest_mtime = max((entry.stat().st_mtime for entry in entries), default=None)
        return {"exists": True, "count": len(entries), "latest_mtime": latest_mtime}

    def _build_snapshot(self) -> dict[str, Any]:
        snapshot: dict[str, Any] = {"signals": capture_signals()}
        enabled = self.config.sources or SUPPORTED_SOURCES
        if "runs" in enabled:
            snapshot["runs"] = self._runs_snapshot()
        if "folder" in enabled:
            snapshot["folder"] = self._folder_snapshot()
        return snapshot

    def _detect_changes(self, current: dict[str, Any]) -> list[dict[str, Any]]:
        if self.previous_snapshot is None:
            return []

        changes: list[dict[str, Any]] = []
        previous = self.previous_snapshot
        enabled = self.config.sources or SUPPORTED_SOURCES

        if "file" in enabled:
            prev_file = previous.get("signals", {}).get("file")
            curr_file = current.get("signals", {}).get("file")
            if prev_file != curr_file:
                changes.append({"source": "file", "before": prev_file, "after": curr_file})

        if "weather" in enabled:
            prev_weather = previous.get("signals", {}).get("weather")
            curr_weather = current.get("signals", {}).get("weather")
            if prev_weather != curr_weather:
                changes.append(
                    {"source": "weather", "before": prev_weather, "after": curr_weather}
                )

        if "runs" in enabled and previous.get("runs") != current.get("runs"):
            changes.append(
                {"source": "runs", "before": previous.get("runs"), "after": current.get("runs")}
            )

        if "folder" in enabled and previous.get("folder") != current.get("folder"):
            changes.append(
                {
                    "source": "folder",
                    "before": previous.get("folder"),
                    "after": current.get("folder"),
                }
            )

        return changes

    def _build_suggestions(self, changes: list[dict[str, Any]]) -> list[str]:
        suggestions: list[str] = []
        for change in changes:
            source = change["source"]
            if source == "file":
                suggestions.append("Valider les nouveaux signaux fichier avant la prochaine run.")
            elif source == "weather":
                suggestions.append("Adapter la stratégie selon les variations météo détectées.")
            elif source == "runs":
                suggestions.append("Relire les derniers runs pour prioriser les actions utiles.")
            elif source == "folder":
                suggestions.append("Analyser les nouveaux artefacts du dossier surveillé.")
        return suggestions

    def _persist_inbox(self, suggestions: list[str]) -> None:
        if not suggestions or self.config.dry_run:
            return

        inbox_path = get_mem_dir() / "inbox.json"
        inbox_path.parent.mkdir(parents=True, exist_ok=True)
        if inbox_path.exists():
            try:
                with inbox_path.open(encoding="utf-8") as handle:
                    payload = json.load(handle)
            except json.JSONDecodeError:
                payload = {"items": []}
        else:
            payload = {"items": []}

        items = payload.get("items", [])
        if not isinstance(items, list):
            items = []

        now = datetime.now(timezone.utc).isoformat()
        for suggestion in suggestions:
            items.append({"created_at": now, "text": suggestion, "source": "watch"})

        payload["items"] = items[-200:]

        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=inbox_path.parent, delete=False
        ) as tmp:
            tmp.write(json.dumps(payload, ensure_ascii=False, indent=2))
            tmp.flush()
            os.fsync(tmp.fileno())
            temp_name = tmp.name

        os.replace(temp_name, inbox_path)

    def tick(self) -> list[dict[str, Any]]:
        """Run one perception/detection/emission cycle."""

        current = self._build_snapshot()
        changes = self._detect_changes(current)

        if changes:
            suggestions = self._build_suggestions(changes)
            event_payload = {
                "changes": changes,
                "suggestions": suggestions,
                "cpu_budget_percent": self.config.cpu_budget_percent,
                "memory_budget_mb": self.config.memory_budget_mb,
                "dry_run": self.config.dry_run,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            self.bus.emit("watch.significant_change", event_payload)
            self._persist_inbox(suggestions)

        self.previous_snapshot = current
        return changes

    def run_forever(self) -> None:
        """Run the daemon loop until interrupted."""

        while True:
            self.tick()
            time.sleep(max(self.config.interval_seconds, 0.1))


def _parse_sources(raw_sources: str | None) -> set[str]:
    if not raw_sources:
        return set(SUPPORTED_SOURCES)
    parts = {part.strip().lower() for part in raw_sources.split(",") if part.strip()}
    unknown = sorted(parts - SUPPORTED_SOURCES)
    if unknown:
        raise ValueError(f"Sources inconnues: {', '.join(unknown)}")
    return parts


def run_watch_daemon(
    *,
    interval_seconds: float,
    sources: str | None,
    cpu_budget_percent: float,
    memory_budget_mb: float,
    dry_run: bool,
    watch_dir: Path | None = None,
) -> int:
    """Entry point used by CLI command ``singular watch``/``singular veille``."""

    try:
        parsed_sources = _parse_sources(sources)
    except ValueError as exc:
        print(str(exc))
        return 1

    daemon = WatchDaemon(
        config=WatchConfig(
            interval_seconds=interval_seconds,
            sources=parsed_sources,
            cpu_budget_percent=cpu_budget_percent,
            memory_budget_mb=memory_budget_mb,
            dry_run=dry_run,
            watch_dir=watch_dir,
        )
    )

    print(
        "Démarrage watch daemon "
        f"(interval={interval_seconds}s, sources={','.join(sorted(parsed_sources))}, "
        f"cpu={cpu_budget_percent}%, mem={memory_budget_mb}MB, dry_run={dry_run})."
    )
    try:
        daemon.run_forever()
    except KeyboardInterrupt:
        print("Watch daemon arrêté.")
    return 0
