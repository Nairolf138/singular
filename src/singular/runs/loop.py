"""Expose :func:`life.loop.run` for the CLI."""

from __future__ import annotations

import random
from pathlib import Path

from singular.life.loop import run


def loop(
    *,
    skills_dir: Path,
    checkpoint: Path,
    budget_seconds: float,
    run_id: str = "loop",
    seed: int | None = None,
) -> None:
    """Wrapper around :func:`life.loop.run` used by the CLI."""

    rng = random.Random(seed) if seed is not None else None
    run(skills_dir, checkpoint, budget_seconds, rng=rng, run_id=run_id)
