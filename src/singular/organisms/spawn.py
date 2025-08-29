"""Spawn command for creating a child organism from two parents."""

from __future__ import annotations

import random
from pathlib import Path

from life.reproduction import crossover


def spawn(parent_a: Path, parent_b: Path, out_dir: Path | None = None, seed: int | None = None) -> Path:
    """Generate a child organism by crossing over two parents.

    Parameters
    ----------
    parent_a, parent_b:
        Paths to the parent skill directories.
    out_dir:
        Directory where the child's skills will be written. If ``None``, a
        directory named ``child`` next to the parents is used.
    seed:
        Optional seed for deterministic behaviour.

    Returns
    -------
    Path
        The directory containing the child's skills.
    """

    rng = random.Random(seed)
    out_dir = out_dir or parent_a.parent / "child"
    out_dir.mkdir(parents=True, exist_ok=True)

    filename, code = crossover(parent_a, parent_b, rng)
    (out_dir / filename).write_text(code, encoding="utf-8")
    return out_dir


def mutation_absurde(code: str) -> str:
    """Return ``code`` with an intentionally useless mutation.

    The transformation appends a meaningless ``0`` expression at the end of
    the module, producing a diff without altering behaviour.  It serves as a
    placeholder for curious but unproductive exploration.
    """

    line = "0  # mutation absurde"
    return code + ("\n" if not code.endswith("\n") else "") + line + "\n"
