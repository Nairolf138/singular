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

# Directory where run logs are stored
RUNS_DIR = Path("runs")


def _ensure_dir(path: Path) -> None:
    """Ensure ``path``'s parent directory exists."""
    path.parent.mkdir(parents=True, exist_ok=True)


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
            "improved": score_new > score_base,
        }
        self._file.write(json.dumps(record) + "\n")
        self._file.flush()
        os.fsync(self._file.fileno())
        self.psyche.process_run_record(record)
        add_episode({"event": "mutation", "mood": self.psyche.last_mood, **record})

    def close(self) -> None:
        """Flush and finalize the log file atomically."""
        if not self._file.closed:
            self._file.flush()
            os.fsync(self._file.fileno())
            self._file.close()
            os.replace(self.tmp_path, self.path)

    def __enter__(self) -> RunLogger:  # pragma: no cover - trivial
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - trivial
        self.close()

