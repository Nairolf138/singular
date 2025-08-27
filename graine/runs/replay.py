from __future__ import annotations

"""Snapshot capture and deterministic replay for evolutionary runs."""

import json
import random
from pathlib import Path
from typing import Any, Dict, List

# Base directories for run artefacts
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
SNAPSHOT_DIR = BASE_DIR / "snapshots"
REPORT_DIR = BASE_DIR / "reports"

for directory in (LOG_DIR, SNAPSHOT_DIR, REPORT_DIR):
    directory.mkdir(parents=True, exist_ok=True)


def _generate_history(seed: int, steps: int) -> List[Dict[str, float]]:
    """Return deterministic objective history using ``seed``."""

    rng = random.Random(seed)
    history: List[Dict[str, float]] = []
    for _ in range(steps):
        history.append({"err": rng.random(), "cost": rng.random()})
    return history


def capture_run(seed: int, name: str, steps: int = 5) -> Path:
    """Generate a run and persist its snapshot and log.

    Parameters
    ----------
    seed:
        Random seed controlling the generated objectives.
    name:
        Name used for snapshot and log filenames.
    steps:
        Number of objective pairs to generate.
    """

    data: Dict[str, Any] = {"seed": seed, "history": _generate_history(seed, steps)}
    snapshot_path = SNAPSHOT_DIR / f"{name}.json"
    log_path = LOG_DIR / f"{name}.log"
    snapshot_path.write_text(json.dumps(data), encoding="utf-8")
    with open(log_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(data) + "\n")
    return snapshot_path


def replay(snapshot_path: Path, seed: int) -> Dict[str, Any]:
    """Replay a previously captured run and verify deterministic behaviour.

    Raises ``RuntimeError`` if the recomputed history differs from the snapshot.
    """

    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    expected = {"seed": seed, "history": _generate_history(seed, len(snapshot["history"]))}
    if snapshot != expected:
        raise RuntimeError("Replay mismatch")
    return expected


__all__ = ["capture_run", "replay", "LOG_DIR", "SNAPSHOT_DIR", "REPORT_DIR"]
