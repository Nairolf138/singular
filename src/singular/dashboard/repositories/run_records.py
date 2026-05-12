from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


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


@dataclass
class RunRecordsRepository:
    """Read dashboard run records from one or many life run directories."""

    base_dir: Path
    runs_path: Path | None
    registry_loader: Callable[[], dict[str, object]]

    def _registry_lives_paths(self) -> list[Path]:
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
        if self.runs_path is not None:
            return [self.runs_path]
        if current_life_only:
            return [self.base_dir / "runs"]
        dirs: list[Path] = []
        seen: set[str] = set()
        for life_dir in self._registry_lives_paths():
            candidate = life_dir / "runs"
            candidate_key = str(candidate.resolve()) if candidate.exists() else str(candidate)
            if candidate_key in seen:
                continue
            seen.add(candidate_key)
            dirs.append(candidate)
        if not dirs:
            dirs.append(self.base_dir / "runs")
        return dirs

    def load_run_records(self, current_life_only: bool = False) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []
        for directory in self.runs_dirs(current_life_only=current_life_only):
            if not directory.exists():
                continue
            for file in directory.iterdir():
                if not file.is_file() or not is_run_jsonl_file(file):
                    continue
                for line in file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    if "_run_file" not in payload:
                        payload["_run_file"] = logical_run_file_stem(file)
                    records.append(payload)
        return records

    def iter_run_files(self, current_life_only: bool = False) -> list[Path]:
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
        records: list[dict[str, object]] = []
        for line in file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                records.append(payload)
        return records

    def latest_run_file(self, current_life_only: bool = False) -> Path | None:
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
            key=lambda path: (path.stat().st_mtime_ns, _latest_ts_in_file(path), path.name),
        )

    def resolve_run_file(self, run_id: str, current_life_only: bool = False) -> Path | None:
        for directory in self.runs_dirs(current_life_only=current_life_only):
            for filename in (f"{run_id}.jsonl", f"{run_id}.jsonl.tmp"):
                candidate = directory / filename
                if candidate.exists():
                    return candidate
            if not directory.exists():
                continue
            for candidate in self.iter_run_files(current_life_only=current_life_only):
                if candidate.parent == directory and logical_run_file_stem(candidate) == run_id:
                    return candidate
        return None

    def resolve_consciousness_path(
        self, run_id: str, current_life_only: bool = False
    ) -> Path | None:
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
