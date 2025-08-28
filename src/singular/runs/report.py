"""Utilities for summarizing run performance."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import json
from typing import Any

from .logger import RUNS_DIR
from ..memory import read_skills, SKILLS_FILE


def load_run_records(run_id: str, runs_dir: Path | str = RUNS_DIR) -> list[dict[str, Any]]:
    """Load run records for ``run_id`` from JSONL log file."""
    runs_dir = Path(runs_dir)
    pattern = f"{run_id}-*.jsonl"
    files = sorted(runs_dir.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No log file found for id {run_id}")
    path = files[-1]
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def report(
    run_id: str,
    *,
    runs_dir: Path | str = RUNS_DIR,
    skills_path: Path | str = SKILLS_FILE,
    seed: int | None = None,
) -> None:
    """Summarize performance for a given run."""

    try:
        records = load_run_records(run_id, runs_dir)
    except FileNotFoundError:
        print(f"No run log found for id {run_id}")
        return

    if not records:
        print(f"No records for id {run_id}")
        return

    scores = [r.get("score_new", 0.0) for r in records]
    ops = [r.get("op", "?") for r in records]

    print(f"Run {run_id}")
    print(f"Generations: {len(scores)}")
    print(f"Final score: {scores[-1]}")
    print(f"Best score: {max(scores)}")

    counter = Counter(ops)
    print("Operator histogram:")
    for op, count in counter.items():
        print(f"  {op}: {count}")

    skills = read_skills(path=skills_path)
    if skills:
        print("Skills:")
        for skill, score in skills.items():
            print(f"  {skill}: {score}")
    else:
        print("No skills recorded.")
