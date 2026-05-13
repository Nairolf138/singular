from __future__ import annotations

import random

from .reproduction import (
    ReproductionDecisionPolicy,
    authorize_reproduction_write,
    crossover,
    decide_reproduction,
)


def pick_crossover_parents(rng: random.Random, world) -> tuple[str, str]:
    """Select reproduction parents, preferring high-reputation organisms."""

    names = list(world.organisms.keys())
    weighted = sorted(
        names,
        key=lambda name: world.reputation.get(name),
        reverse=True,
    )
    primary = weighted[0]
    remaining = [name for name in names if name != primary]
    return primary, rng.choice(remaining)


_pick_crossover_parents = pick_crossover_parents

__all__ = [
    "ReproductionDecisionPolicy",
    "authorize_reproduction_write",
    "crossover",
    "decide_reproduction",
    "pick_crossover_parents",
    "_pick_crossover_parents",
]
