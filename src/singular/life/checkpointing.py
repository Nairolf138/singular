from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Mapping

log = logging.getLogger(__name__)

CHECKPOINT_VERSION = 1


@dataclass
class Checkpoint:
    """Simple persistent state for the evolutionary loop."""

    version: int = 1
    iteration: int = 0
    stats: Dict[str, Dict[str, float]] = field(default_factory=dict)
    health_history: list[dict[str, float | int]] = field(default_factory=list)
    health_counters: dict[str, float | int] = field(default_factory=dict)


def _migrate_checkpoint_data(data: Mapping[str, object]) -> dict[str, object]:
    """Migrate checkpoint payload to the current schema version."""

    migrated = dict(data)
    version = migrated.get("version")
    if not isinstance(version, int):
        version = 0

    if version < 1:
        migrated["version"] = 1
        version = 1

    # Keep final payload aligned with current application schema.
    migrated["version"] = CHECKPOINT_VERSION
    return migrated


def _checkpoint_from_data(data: Mapping[str, object]) -> Checkpoint:
    """Build a :class:`Checkpoint` from raw persisted data safely."""

    migrated = _migrate_checkpoint_data(data)
    defaults = asdict(Checkpoint())
    payload = {**defaults, **migrated}
    allowed_keys = set(Checkpoint.__dataclass_fields__)
    filtered_payload = {key: value for key, value in payload.items() if key in allowed_keys}
    return Checkpoint(**filtered_payload)


def load_checkpoint(path: Path) -> Checkpoint:
    """Load checkpoint state from *path* if it exists."""

    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, json.JSONDecodeError) as exc:
            log.warning("failed to load checkpoint from %s: %s", path, exc)
        else:
            if isinstance(data, Mapping):
                return _checkpoint_from_data(data)
            log.warning("failed to load checkpoint from %s: root must be an object", path)
    return Checkpoint()


def save_checkpoint(path: Path, state: Checkpoint) -> None:
    """Persist *state* to *path*."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state)), encoding="utf-8")
