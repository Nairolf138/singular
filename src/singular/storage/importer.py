"""Import legacy JSON/JSONL artifacts into SQLite storage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .sqlite import (
    EpisodesRepository,
    RunsRepository,
    SQLiteStorage,
    StorageConfig,
    WorldStateRepository,
)


def _read_jsonl(path: Path):
    if not path.exists():
        return
    for lineno, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            yield lineno, payload


def _run_id_from_path(path: Path) -> str:
    if path.name == "events.jsonl" and path.parent.name:
        return path.parent.name
    name = path.name
    for suffix in (".jsonl.tmp", ".jsonl"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    if "-" in name:
        base, tail = name.rsplit("-", 1)
        if base and tail.isdigit() and len(tail) >= 8:
            return base
    return name or "unknown"


def import_legacy_storage(
    root: Path | str, *, db_path: Path | str | None = None
) -> dict[str, int]:
    root = Path(root)
    storage = SQLiteStorage(
        StorageConfig(root=root, db_path=Path(db_path) if db_path else None)
    )
    counts = {"episodes": 0, "world_state_snapshots": 0, "run_events": 0}

    episodes = EpisodesRepository(storage)
    ep_path = root / "mem" / "episodic.jsonl"
    for lineno, payload in _read_jsonl(ep_path) or []:
        episodes.add(payload, source_path=str(ep_path), source_line=lineno)
        counts["episodes"] += 1

    world_path = root / "mem" / "world_state.json"
    if world_path.exists():
        try:
            payload: Any = json.loads(world_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            WorldStateRepository(storage).save_snapshot(
                payload, source_path=str(world_path)
            )
            counts["world_state_snapshots"] += 1

    runs_repo = RunsRepository(storage)
    runs_dir = root / "runs"
    if runs_dir.exists():
        run_files = (
            list(runs_dir.glob("*.jsonl"))
            + list(runs_dir.glob("*.jsonl.tmp"))
            + list(runs_dir.glob("*/events.jsonl"))
        )
        for run_file in sorted(set(run_files)):
            for lineno, payload in _read_jsonl(run_file) or []:
                if "payload" in payload and isinstance(payload.get("payload"), dict):
                    event_type = str(payload.get("event_type") or "") or None
                    payload = {
                        **payload["payload"],
                        "_event_type": event_type,
                        "_ts": payload.get("ts"),
                    }
                else:
                    event_type = (
                        str(payload.get("event") or payload.get("_event_type") or "")
                        or None
                    )
                runs_repo.add_event(
                    _run_id_from_path(run_file),
                    payload,
                    event_type=event_type,
                    source_path=str(run_file),
                    source_line=lineno,
                )
                counts["run_events"] += 1
    return counts
