"""Spawn command for creating a child organism from two parents."""

from __future__ import annotations

import json
import random
from pathlib import Path

from singular.life.reproduction import (
    InheritanceRules,
    ReproductionVariationPolicy,
    compute_parent_compatibility,
    crossover,
    inherit_episodic_memory,
    inherit_psyche,
    inherit_values,
)
from singular.memory import read_episodes, read_psyche, read_values, write_psyche, write_values


def spawn(
    parent_a: Path,
    parent_b: Path,
    out_dir: Path | None = None,
    seed: int | None = None,
    variation_policy: ReproductionVariationPolicy | None = None,
    inheritance_rules: InheritanceRules | None = None,
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
    variation_policy = variation_policy or ReproductionVariationPolicy()
    inheritance_rules = inheritance_rules or InheritanceRules()

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
    compatibility = compute_parent_compatibility(psyche_a, psyche_b)
    if compatibility < variation_policy.compatibility_threshold:
        raise ValueError(
            "parent compatibility below threshold: "
            f"{compatibility:.2f} < {variation_policy.compatibility_threshold:.2f}"
        )

    child_psyche = inherit_psyche(
        psyche_a,
        psyche_b,
        rng=rng,
        policy=variation_policy,
    )

    write_psyche(child_psyche, out_dir / "mem" / "psyche.json")

    values_a = read_values(parent_a / "mem" / "values.yaml")
    values_b = read_values(parent_b / "mem" / "values.yaml")
    child_values = inherit_values(values_a, values_b, rng=rng, policy=variation_policy)
    if child_values:
        write_values(child_values, out_dir / "mem" / "values.yaml")

    memory_a = read_episodes(parent_a / "mem" / "episodic.jsonl")
    memory_b = read_episodes(parent_b / "mem" / "episodic.jsonl")
    inherited_episodes = inherit_episodic_memory(
        memory_a,
        memory_b,
        rng=rng,
        rules=inheritance_rules,
    )
    if inherited_episodes:
        episodic_file = out_dir / "mem" / "episodic.jsonl"
        episodic_file.parent.mkdir(parents=True, exist_ok=True)
        lines = "\n".join(json.dumps(ep, ensure_ascii=False) for ep in inherited_episodes)
        episodic_file.write_text(lines + "\n", encoding="utf-8")
    return out_dir


def mutation_absurde(code: str) -> str:
    """Return ``code`` with an intentionally useless mutation.

    The transformation appends a meaningless ``0`` expression at the end of
    the module, producing a diff without altering behaviour.  It serves as a
    placeholder for curious but unproductive exploration.
    """

    line = "0  # mutation absurde"
    return code + ("\n" if not code.endswith("\n") else "") + line + "\n"
