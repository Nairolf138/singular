"""Spawn command for creating a child organism from two parents."""

from __future__ import annotations

import random
from pathlib import Path

from singular.life.reproduction import crossover
from singular.memory import read_psyche, write_psyche


def spawn(
    parent_a: Path,
    parent_b: Path,
    out_dir: Path | None = None,
    seed: int | None = None,
) -> Path:
    """Generate a child organism by crossing over two parents.

    Parameters
    ----------
    parent_a, parent_b:
        Paths to the parent organism directories containing ``skills`` and
        ``mem/psyche.json``.
    out_dir:
        Directory where the child's data will be written. If ``None``, a
        directory named ``child`` next to the parents is used.
    seed:
        Optional seed for deterministic behaviour.

    Returns
    -------
    Path
        The directory containing the child's data.
    """

    rng = random.Random(seed)
    out_dir = out_dir or parent_a.parent / "child"

    # ------------------------------------------------------------------
    # Generate hybrid skill
    # ------------------------------------------------------------------
    skills_out = out_dir / "skills"
    skills_out.mkdir(parents=True, exist_ok=True)
    filename, code = crossover(parent_a / "skills", parent_b / "skills", rng)
    (skills_out / filename).write_text(code, encoding="utf-8")

    # ------------------------------------------------------------------
    # Combine parental psyches
    # ------------------------------------------------------------------
    psyche_a = read_psyche(parent_a / "mem" / "psyche.json")
    psyche_b = read_psyche(parent_b / "mem" / "psyche.json")

    child_psyche: dict[str, object] = {}
    keys = set(psyche_a) | set(psyche_b)
    for key in keys:
        val_a = psyche_a.get(key)
        val_b = psyche_b.get(key)
        if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
            child_psyche[key] = (val_a + val_b) / 2
        else:
            options = [v for v in (val_a, val_b) if v is not None]
            if options:
                child_psyche[key] = rng.choice(options)

    write_psyche(child_psyche, out_dir / "mem" / "psyche.json")
    return out_dir


def mutation_absurde(code: str) -> str:
    """Return ``code`` with an intentionally useless mutation.

    The transformation appends a meaningless ``0`` expression at the end of
    the module, producing a diff without altering behaviour.  It serves as a
    placeholder for curious but unproductive exploration.
    """

    line = "0  # mutation absurde"
    return code + ("\n" if not code.endswith("\n") else "") + line + "\n"
