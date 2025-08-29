"""Utilities for recording execution runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import json
import os
from typing import Any

from ..psyche import Psyche
from ..memory import add_episode
from typing import Callable, Dict

# Base directory for persistent files
_BASE_DIR = Path(os.environ.get("SINGULAR_HOME", "."))
# Directory where run logs are stored
RUNS_DIR = _BASE_DIR / "runs"
# Number of run logs to retain
MAX_RUN_LOGS = int(os.environ.get("SINGULAR_RUNS_KEEP", "20"))

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
    ) -> None:
        """Append a record to the log file.

        The line is flushed and fsynced to guarantee durability.
        """

        record: dict[str, Any] = {
            "ts": datetime.utcnow().isoformat(timespec="seconds"),
            "skill": skill,
            "op": op,
            "diff": diff,
            "ok": ok,
            "ms_base": ms_base,
            "ms_new": ms_new,
            "score_base": score_base,
            "score_new": score_new,
            # ``improved`` is ``True`` when the new score is lower than the
            # baseline score.  Lower values indicate better performance.
            "improved": score_new < score_base,
        }
        self._file.write(json.dumps(record) + "\n")
        self._file.flush()
        os.fsync(self._file.fileno())
        self.psyche.process_run_record(record)
        mood = getattr(self.psyche, "last_mood", None)
        add_episode(
            {"event": "mutation", "mood": mood, **record}, mood_styles=mood_styles
        )

    def log_death(self, reason: str, **info: Any) -> None:
        """Record a death event with optional additional information."""

        record: dict[str, Any] = {
            "ts": datetime.utcnow().isoformat(timespec="seconds"),
            "event": "death",
            "reason": reason,
            **info,
        }
        self._file.write(json.dumps(record) + "\n")
        self._file.flush()
        os.fsync(self._file.fileno())
        add_episode(record)

    def log_refusal(self, skill: str) -> None:
        """Record a refusal to mutate ``skill``."""

        record: dict[str, Any] = {
            "ts": datetime.utcnow().isoformat(timespec="seconds"),
            "event": "refuse",
            "skill": skill,
        }
        self._file.write(json.dumps(record) + "\n")
        self._file.flush()
        os.fsync(self._file.fileno())
        add_episode(record)

    def log_delay(self, skill: str, resume_at: float) -> None:
        """Record a procrastination event for ``skill``."""

        record: dict[str, Any] = {
            "ts": datetime.utcnow().isoformat(timespec="seconds"),
            "event": "delay",
            "skill": skill,
            "resume_at": resume_at,
        }
        self._file.write(json.dumps(record) + "\n")
        self._file.flush()
        os.fsync(self._file.fileno())
        add_episode(record)

    def log_absurde(self, skill: str, diff: str) -> None:
        """Record an absurd mutation event."""

        record: dict[str, Any] = {
            "ts": datetime.utcnow().isoformat(timespec="seconds"),
            "event": "absurde",
            "skill": skill,
            "diff": diff,
        }
        self._file.write(json.dumps(record) + "\n")
        self._file.flush()
        os.fsync(self._file.fileno())
        add_episode(record)

    def close(self) -> None:
        """Flush and finalize the log file atomically."""
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
