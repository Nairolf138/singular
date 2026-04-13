"""Utilities for recording execution runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import json
import logging
import os
from typing import Any

from ..psyche import Psyche
from ..memory import add_episode, add_procedural_memory
from typing import Callable, Dict

# Base directory for persistent files
_BASE_DIR = Path(os.environ.get("SINGULAR_HOME", "."))
# Directory where run logs are stored
RUNS_DIR = _BASE_DIR / "runs"
# Number of run logs to retain
MAX_RUN_LOGS = int(os.environ.get("SINGULAR_RUNS_KEEP", "20"))
EVENT_SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# Mood style helpers
# ---------------------------------------------------------------------------


def _style_colere(mood: str) -> str:
    """Rendering for the ``colere`` (anger) mood."""

    return mood.upper()


def _style_fatigue(mood: str) -> str:
    """Rendering for the ``fatigue`` (tired) mood."""

    return f"{mood}..."


def _style_neutre(mood: str) -> str:
    """Rendering for the ``neutre`` (neutral) mood."""

    return mood


mood_styles: Dict[str | None, Callable[[str], str]] = {
    "colere": _style_colere,
    "colère": _style_colere,
    "fatigue": _style_fatigue,
    "neutre": _style_neutre,
    None: _style_neutre,
}

_provider_logger = logging.getLogger("singular.provider")


def log_provider_event(
    *,
    provider: str,
    latency_ms: float,
    fallback: bool,
    error_category: str | None,
) -> None:
    """Emit a structured provider log entry."""

    payload = {
        "event": "provider_call",
        "provider": provider,
        "latency_ms": round(latency_ms, 2),
        "fallback": fallback,
        "error_category": error_category,
    }
    _provider_logger.info("provider_call", extra={"payload": payload})


def _ensure_dir(path: Path) -> None:
    """Ensure ``path``'s parent directory exists."""
    path.parent.mkdir(parents=True, exist_ok=True)


def _enforce_retention(root: Path, keep: int = MAX_RUN_LOGS) -> None:
    """Remove oldest log files beyond the retention limit."""
    logs = sorted(
        root.glob("*.jsonl"),
        key=lambda p: (p.stat().st_mtime, p.name),
        reverse=True,
    )
    for old in logs[keep:]:
        try:
            old.unlink()
        except FileNotFoundError:  # pragma: no cover - race condition
            pass
    # Clean up any leftover temporary files
    tmps = sorted(
        root.glob("*.jsonl.tmp"),
        key=lambda p: (p.stat().st_mtime, p.name),
        reverse=True,
    )
    for old in tmps[keep:]:
        try:
            old.unlink()
        except FileNotFoundError:  # pragma: no cover - race condition
            pass


@dataclass
class RunLogger:
    """Append JSONL run records with crash recovery.

    Parameters
    ----------
    run_id:
        Identifier for the run.
    root:
        Directory in which log files are written. Defaults to :data:`RUNS_DIR`.
    """

    run_id: str
    root: Path = RUNS_DIR
    psyche: Psyche = field(default_factory=Psyche.load_state)

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        _enforce_retention(self.root)

        self.run_dir = self.root / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.run_dir / "events.jsonl"
        self._events_file = self.events_path.open("a", encoding="utf-8")
        self.consciousness_path = self.run_dir / "consciousness.jsonl"
        self._consciousness_file = self.consciousness_path.open("a", encoding="utf-8")

        # Resume from existing temporary file if present
        tmp_pattern = f"{self.run_id}-*.jsonl.tmp"
        existing = sorted(self.root.glob(tmp_pattern))
        if existing:
            self.tmp_path = existing[-1]
            # derive final path and timestamp from tmp file name
            self.path = self.tmp_path.with_suffix("")
            stem = self.path.name
            # stem is <id>-<timestamp>
            self.timestamp = stem.split("-", 1)[1]
            self._file = self.tmp_path.open("a", encoding="utf-8")
        else:
            self.timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            self.path = self.root / f"{self.run_id}-{self.timestamp}.jsonl"
            self.tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
            _ensure_dir(self.tmp_path)
            self._file = self.tmp_path.open("a", encoding="utf-8")

    def _write_record(self, record: dict[str, Any]) -> None:
        self._file.write(json.dumps(record) + "\n")
        self._file.flush()
        os.fsync(self._file.fileno())

    def _write_event(self, event_type: str, payload: dict[str, Any], ts: str) -> None:
        event = {
            "version": EVENT_SCHEMA_VERSION,
            "event_type": event_type,
            "ts": ts,
            "payload": payload,
        }
        self._events_file.write(json.dumps(event) + "\n")
        self._events_file.flush()
        os.fsync(self._events_file.fileno())

    def log_consciousness(
        self,
        *,
        perception_summary: str,
        evaluated_hypotheses: list[dict[str, Any]],
        final_choice: str | None,
        justification: str,
        objective: str | None = None,
        mood: str | None = None,
        energy: float | None = None,
        success: bool | None = None,
    ) -> None:
        """Record a reflection event in ``runs/<run_id>/consciousness.jsonl``."""

        ts = datetime.utcnow().isoformat(timespec="seconds")
        record: dict[str, Any] = {
            "ts": ts,
            "event": "consciousness",
            "perception_summary": perception_summary,
            "evaluated_hypotheses": evaluated_hypotheses,
            "final_choice": final_choice,
            "justification": justification,
            "objective": objective,
            "emotional_state": {
                "mood": mood,
                "energy": energy,
            },
            "success": success,
        }
        self._consciousness_file.write(json.dumps(record) + "\n")
        self._consciousness_file.flush()
        os.fsync(self._consciousness_file.fileno())

    def log(
        self,
        skill: str,
        op: str,
        diff: str,
        ok: bool,
        ms_base: float,
        ms_new: float,
        score_base: float,
        score_new: float,
        *,
        impacted_file: str | None = None,
        decision_reason: str | None = None,
        alternative_scores: list[tuple[int, str, float]] | None = None,
        human_summary: str | None = None,
        loop_modifications: dict[str, int] | None = None,
        health: dict[str, float | int] | None = None,
    ) -> None:
        """Append a mutation record to the log file."""

        ts = datetime.utcnow().isoformat(timespec="seconds")
        record: dict[str, Any] = {
            "ts": ts,
            "skill": skill,
            "op": op,
            "diff": diff,
            "ok": ok,
            "ms_base": ms_base,
            "ms_new": ms_new,
            "score_base": score_base,
            "score_new": score_new,
            "improved": score_new < score_base,
            "impacted_file": impacted_file,
            "decision_reason": decision_reason,
            "alternative_scores": alternative_scores or [],
            "human_summary": human_summary,
            "loop_modifications": loop_modifications or {},
            "health": health or {},
        }
        self._write_record(record)
        self._write_event("mutation", record, ts)

        self.psyche.process_run_record(record)
        mood = getattr(self.psyche, "last_mood", None)
        mood_val = getattr(mood, "value", mood)
        add_episode(
            {"event": "mutation", "mood": mood_val, **record}, mood_styles=mood_styles
        )
        add_procedural_memory(record)

    def log_death(self, reason: str, **info: Any) -> None:
        """Record a death event with optional additional information."""

        record: dict[str, Any] = {
            "ts": datetime.utcnow().isoformat(timespec="seconds"),
            "event": "death",
            "reason": reason,
            **info,
        }
        self._write_record(record)
        self._write_event("death", record, record["ts"])
        add_episode(record)

    def log_refusal(self, skill: str) -> None:
        """Record a refusal to mutate ``skill``."""

        record: dict[str, Any] = {
            "ts": datetime.utcnow().isoformat(timespec="seconds"),
            "event": "refuse",
            "skill": skill,
        }
        self._write_record(record)
        self._write_event("refuse", record, record["ts"])
        add_episode(record)

    def log_delay(self, skill: str, resume_at: float) -> None:
        """Record a procrastination event for ``skill``."""

        record: dict[str, Any] = {
            "ts": datetime.utcnow().isoformat(timespec="seconds"),
            "event": "delay",
            "skill": skill,
            "resume_at": resume_at,
        }
        self._write_record(record)
        self._write_event("delay", record, record["ts"])
        add_episode(record)

    def log_absurde(self, skill: str, diff: str) -> None:
        """Record an absurd mutation event."""

        record: dict[str, Any] = {
            "ts": datetime.utcnow().isoformat(timespec="seconds"),
            "event": "absurde",
            "skill": skill,
            "diff": diff,
        }
        self._write_record(record)
        self._write_event("absurde", record, record["ts"])
        add_episode(record)

    def log_interaction(self, event: str, **info: Any) -> None:
        """Record an explicit ecosystem interaction event."""

        record: dict[str, Any] = {
            "ts": datetime.utcnow().isoformat(timespec="seconds"),
            "event": "interaction",
            "interaction": event,
            **info,
        }
        self._write_record(record)
        self._write_event("interaction", record, record["ts"])
        add_episode(record)

    def log_test_coevolution(
        self,
        *,
        skill: str,
        accepted: bool,
        pool_size: int,
        added: int,
        removed: int,
        detection_rate: float,
        score_base: float,
        score_new: float,
        score_combined_base: float,
        score_combined_new: float,
    ) -> None:
        """Record co-evolution decisions for the living test pool."""

        record: dict[str, Any] = {
            "ts": datetime.utcnow().isoformat(timespec="seconds"),
            "event": "test_coevolution",
            "skill": skill,
            "accepted": accepted,
            "pool_size": pool_size,
            "tests_added": added,
            "tests_removed": removed,
            "regression_detection_rate": detection_rate,
            "score_base": score_base,
            "score_new": score_new,
            "score_combined_base": score_combined_base,
            "score_combined_new": score_combined_new,
        }
        self._write_record(record)
        self._write_event("test_coevolution", record, record["ts"])
        add_episode(record)

    def close(self) -> None:
        """Flush and finalize the log files atomically."""
        if not self._consciousness_file.closed:
            self._consciousness_file.flush()
            os.fsync(self._consciousness_file.fileno())
            self._consciousness_file.close()
        if not self._events_file.closed:
            self._events_file.flush()
            os.fsync(self._events_file.fileno())
            self._events_file.close()
        if not self._file.closed:
            self._file.flush()
            os.fsync(self._file.fileno())
            self._file.close()
            os.replace(self.tmp_path, self.path)
            _enforce_retention(self.root)

    def __enter__(self) -> RunLogger:  # pragma: no cover - trivial
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - trivial
        self.close()
