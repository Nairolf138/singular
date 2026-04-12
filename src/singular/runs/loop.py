"""Expose :func:`life.loop.run` for the CLI."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Iterable, Mapping

from singular.life.loop import run


def loop(
    *,
    skills_dir: Path | None = None,
    skills_dirs: Mapping[str, Path] | Iterable[Path] | None = None,
    checkpoint: Path,
    budget_seconds: float,
    run_id: str = "loop",
    seed: int | None = None,
) -> None:
    """Wrapper around :func:`life.loop.run` used by the CLI.

    Accepts either:
    - ``skills_dir`` for backward-compatible single-organism runs.
    - ``skills_dirs`` for multi-organism runs (iterable or explicit mapping).
    """

    rng = random.Random(seed) if seed is not None else None
    if skills_dirs is None:
        if skills_dir is None:
            raise ValueError("skills_dir or skills_dirs must be provided")
        payload: Mapping[str, Path] | Iterable[Path] | Path = skills_dir
    else:
        payload = skills_dirs
    run(payload, checkpoint, budget_seconds, rng=rng, run_id=run_id)
