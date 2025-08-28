"""Snapshot capture and deterministic replay for evolutionary runs."""

from __future__ import annotations

import json
import random
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List

# Base directories for run artefacts
BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
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
    """Generate a run snapshot including code, tests and configuration."""

    run_id = f"{name}-{uuid.uuid4().hex[:8]}"
    run_dir = SNAPSHOT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    data: Dict[str, Any] = {"seed": seed, "history": _generate_history(seed, steps)}
    snapshot_path = run_dir / "snapshot.json"
    snapshot_path.write_text(json.dumps(data), encoding="utf-8")

    # Persist seed and configuration
    (run_dir / "seeds.json").write_text(json.dumps({"seed": seed}), encoding="utf-8")
    (run_dir / "config.json").write_text(json.dumps({"steps": steps}), encoding="utf-8")

    # Copy source code and tests for reproducibility
    code_dir = run_dir / "code"
    code_dir.mkdir(parents=True, exist_ok=True)
    for folder in ["kernel", "evolver", "meta", "target"]:
        shutil.copytree(ROOT_DIR / folder, code_dir / folder)
    shutil.copytree(ROOT_DIR / "tests", run_dir / "tests")
    shutil.copytree(ROOT_DIR / "configs", run_dir / "configs")

    # Log capture event with hashed JSONL logger
    from ..kernel.logger import JsonlLogger

    logger = JsonlLogger(LOG_DIR / f"{run_id}.log")
    logger.log({"event": "capture", "seed": seed, "steps": steps, "snapshot": snapshot_path.name})

    return snapshot_path


def replay(snapshot_path: Path) -> Dict[str, Any]:
    """Replay a previously captured run using the stored seed and config.

    Parameters
    ----------
    snapshot_path:
        Path to ``snapshot.json`` inside the captured run directory.

    Returns
    -------
    Dict[str, Any]
        The regenerated run data.

    Raises
    ------
    RuntimeError
        If the regenerated data differ from the snapshot (non-deterministic).
    """

    run_dir = snapshot_path.parent
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))

    # Load seed and configuration
    seed_data = json.loads((run_dir / "seeds.json").read_text(encoding="utf-8"))
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    seed = seed_data["seed"]
    steps = int(config.get("steps", len(snapshot["history"])))

    expected = {"seed": seed, "history": _generate_history(seed, steps)}
    if snapshot != expected:
        raise RuntimeError("Replay mismatch")

    # Log replay event
    from ..kernel.logger import JsonlLogger

    run_id = run_dir.name
    logger = JsonlLogger(LOG_DIR / f"{run_id}.log")
    logger.log({"event": "replay", "seed": seed, "steps": steps, "snapshot": snapshot_path.name})

    return expected


__all__ = ["capture_run", "replay", "LOG_DIR", "SNAPSHOT_DIR", "REPORT_DIR"]
