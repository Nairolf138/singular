"""Repository helpers for dashboard run logs.

Centralizes path discovery, tolerant JSONL parsing, `.jsonl.tmp` handling, and
active-life resolution for dashboard routes and services.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from ...storage import RunsRepository, SQLiteStorage, StorageConfig


def is_run_jsonl_file(path: Path) -> bool:
    """Return whether *path* is a persisted or in-progress run JSONL file."""

    name = path.name
    return (
        not name.endswith(".consciousness.jsonl")
        and not name.endswith(".consciousness.jsonl.tmp")
        and (name.endswith(".jsonl") or name.endswith(".jsonl.tmp"))
    )


def logical_run_file_stem(path: Path) -> str:
    """Return the logical run identifier represented by a run JSONL path."""

    stem = path.name
    if stem.endswith(".jsonl.tmp"):
        stem = stem[: -len(".jsonl.tmp")]
    elif stem.endswith(".jsonl"):
        stem = stem[: -len(".jsonl")]
    else:
        stem = path.stem

    normalized = stem.strip()
    if not normalized:
        return "unknown"

    if "-" in normalized:
        candidate, suffix = normalized.rsplit("-", 1)
        if candidate and suffix.isdigit() and len(suffix) >= 8:
            return candidate
    return normalized


def resolve_current_life_home(
    registry_loader: Callable[[], dict[str, object]],
    fallback_base_dir: Path,
) -> Path:
    """Resolve the active life directory from the registry, with a stable fallback."""

    fallback_home = Path(os.environ.get("SINGULAR_HOME", str(fallback_base_dir)))
    try:
        registry = registry_loader()
    except Exception:
        return fallback_home

    active = registry.get("active")
    raw_lives = registry.get("lives")
    if not isinstance(active, str) or not isinstance(raw_lives, dict):
        return fallback_home

    active_meta = raw_lives.get(active)
    path_value = getattr(active_meta, "path", None)
    if isinstance(active_meta, dict):
        path_value = active_meta.get("path", path_value)
    if isinstance(path_value, str):
        path_value = Path(path_value)
    if isinstance(path_value, Path):
        return path_value

    return fallback_home


@dataclass
class RunRecordsRepository:
    """Read dashboard run records from one or many life run directories."""

    base_dir: Path
    runs_path: Path | None
    registry_loader: Callable[[], dict[str, object]]

    @staticmethod
    def _limit(name: str, default: int) -> int:
        try:
            return max(1, int(os.environ.get(name, default)))
        except ValueError:
            return default

    def iter_jsonl_records(
        self,
        file: Path,
        *,
        max_lines: int | None = None,
        max_bytes: int | None = None,
        max_event_bytes: int | None = None,
    ) -> Iterator[dict[str, object]]:
        """Yield JSON objects without ever materializing a whole log or huge line."""
        lines_left = max_lines or self._limit("SINGULAR_DASHBOARD_MAX_LINES", 10_000)
        bytes_left = max_bytes or self._limit(
            "SINGULAR_DASHBOARD_MAX_BYTES", 16 * 1024 * 1024
        )
        event_limit = max_event_bytes or self._limit(
            "SINGULAR_DASHBOARD_MAX_EVENT_BYTES", 1024 * 1024
        )
        with file.open("rb") as handle:
            while lines_left > 0 and bytes_left > 0:
                raw = handle.readline(min(event_limit + 1, bytes_left + 1))
                if not raw:
                    break
                consumed = len(raw)
                bytes_left -= consumed
                lines_left -= 1
                oversized = len(raw) > event_limit or (
                    not raw.endswith(b"\n") and consumed > bytes_left
                )
                if len(raw) > event_limit and not raw.endswith(b"\n"):
                    # Drain the physical line in bounded chunks; never parse fragments.
                    while bytes_left > 0:
                        chunk = handle.readline(min(event_limit + 1, bytes_left))
                        bytes_left -= len(chunk)
                        if not chunk or chunk.endswith(b"\n"):
                            break
                if oversized:
                    continue
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if isinstance(payload, dict):
                    yield payload

    def _registry_lives_paths(self) -> list[Path]:
        """Return life home directories declared in the registry."""
        registry = self.registry_loader()
        raw_lives = registry.get("lives")
        if not isinstance(raw_lives, dict):
            return []
        lives_paths: list[Path] = []
        for meta in raw_lives.values():
            path_value = getattr(meta, "path", None)
            if isinstance(meta, dict):
                path_value = meta.get("path", path_value)
            if isinstance(path_value, str):
                path_value = Path(path_value)
            if isinstance(path_value, Path):
                lives_paths.append(path_value)
        return lives_paths

    def runs_dirs(self, current_life_only: bool = False) -> list[Path]:
        """Return run directories for explicit, active-life, or registry-wide scope."""
        if self.runs_path is not None:
            return [self.runs_path]
        if current_life_only:
            current_life_home = resolve_current_life_home(
                self.registry_loader,
                self.base_dir,
            )
            return [current_life_home / "runs"]
        dirs: list[Path] = []
        seen: set[str] = set()
        for life_dir in self._registry_lives_paths():
            candidate = life_dir / "runs"
            candidate_key = (
                str(candidate.resolve()) if candidate.exists() else str(candidate)
            )
            if candidate_key in seen:
                continue
            seen.add(candidate_key)
            dirs.append(candidate)
        if not dirs:
            dirs.append(self.base_dir / "runs")
        return dirs

    def load_run_records(
        self, current_life_only: bool = False
    ) -> list[dict[str, object]]:
        """Load valid records and annotate each one with its logical run id."""
        db_path = self.base_dir / "mem" / "singular.sqlite3"
        if db_path.exists():
            sqlite_records = RunsRepository(
                SQLiteStorage(StorageConfig(root=self.base_dir, db_path=db_path))
            ).list_events()
            if sqlite_records:
                return sqlite_records
        records: list[dict[str, object]] = []
        for directory in self.runs_dirs(current_life_only=current_life_only):
            if not directory.exists():
                continue
            for file in directory.iterdir():
                if not file.is_file() or not is_run_jsonl_file(file):
                    continue
                for payload in self.iter_jsonl_records(file):
                    if "_run_file" not in payload:
                        payload["_run_file"] = logical_run_file_stem(file)
                    records.append(payload)
        return records

    def iter_run_files(self, current_life_only: bool = False) -> list[Path]:
        """List run JSONL files sorted by modification time then filename."""
        files: list[Path] = []
        for directory in self.runs_dirs(current_life_only=current_life_only):
            if not directory.exists():
                continue
            for path in directory.iterdir():
                if path.is_file() and is_run_jsonl_file(path):
                    files.append(path)
        return sorted(
            files,
            key=lambda path: (path.stat().st_mtime_ns, path.name),
        )

    def read_jsonl_records(self, file: Path) -> list[dict[str, object]]:
        """Read JSON objects from one JSONL file while ignoring malformed lines."""
        records: list[dict[str, object]] = []
        records.extend(self.iter_jsonl_records(file))
        return records

    def latest_run_file(self, current_life_only: bool = False) -> Path | None:
        """Return the most recent run file by mtime, record timestamp, and name."""
        files = self.iter_run_files(current_life_only=current_life_only)
        if not files:
            return None

        def _latest_ts_in_file(path: Path) -> str:
            latest_ts = ""
            for record in self.read_jsonl_records(path):
                ts = record.get("ts")
                if isinstance(ts, str) and ts > latest_ts:
                    latest_ts = ts
            return latest_ts

        return max(
            files,
            key=lambda path: (
                path.stat().st_mtime_ns,
                _latest_ts_in_file(path),
                path.name,
            ),
        )

    def resolve_run_file(
        self, run_id: str, current_life_only: bool = False
    ) -> Path | None:
        """Resolve a logical run id to persisted or in-progress JSONL storage."""
        for directory in self.runs_dirs(current_life_only=current_life_only):
            for filename in (f"{run_id}.jsonl", f"{run_id}.jsonl.tmp"):
                candidate = directory / filename
                if candidate.exists():
                    return candidate
            if not directory.exists():
                continue
            for candidate in self.iter_run_files(current_life_only=current_life_only):
                if (
                    candidate.parent == directory
                    and logical_run_file_stem(candidate) == run_id
                ):
                    return candidate
        return None

    def resolve_consciousness_path(
        self, run_id: str, current_life_only: bool = False
    ) -> Path | None:
        """Resolve the companion consciousness log for a run id, if present."""
        raw_run_id = run_id
        if "-" in raw_run_id:
            candidate_id, suffix = raw_run_id.rsplit("-", 1)
            if candidate_id and suffix.isdigit() and len(suffix) >= 8:
                raw_run_id = candidate_id
        candidate_ids = [raw_run_id]
        if run_id not in candidate_ids:
            candidate_ids.append(run_id)
        for directory in self.runs_dirs(current_life_only=current_life_only):
            for candidate_id in candidate_ids:
                candidates = (
                    directory / candidate_id / "consciousness.jsonl",
                    directory / f"{candidate_id}.consciousness.jsonl",
                    directory / f"{candidate_id}.consciousness.jsonl.tmp",
                )
                for candidate in candidates:
                    if candidate.exists():
                        return candidate
        return None
