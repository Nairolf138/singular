from __future__ import annotations

from random import Random
from typing import Dict

from .dsl import MetaSpec, MAX_POPULATION_CAP, SELECTION_STRATEGIES


def _renormalize(dist: Dict[str, float]) -> None:
    if not dist:
        return
    total = 0.0
    for k, v in dist.items():
        if v < 0:
            v = 0.0
        dist[k] = v
        total += v
    if total == 0:
        share = 1.0 / len(dist)
        for k in dist:
            dist[k] = share
        return
    for k in dist:
        dist[k] /= total


def propose_mutation(
    spec: MetaSpec, delta: float = 0.1, rng: Random | None = None
) -> MetaSpec:
    """Propose an allowed architectural patch over mutable meta-surfaces."""

    rng = rng or Random()

    new_spec = MetaSpec(
        weights=dict(spec.weights),
        operator_mix=dict(spec.operator_mix),
        population_cap=spec.population_cap,
        selection_strategy=spec.selection_strategy,
        diff_max=spec.diff_max,
        forbidden=list(spec.forbidden),
    )

    if len(new_spec.weights) >= 1:
        key = rng.choice(list(new_spec.weights.keys()))
        new_spec.weights[key] += rng.uniform(-delta, delta)
        _renormalize(new_spec.weights)

    if len(new_spec.operator_mix) >= 1:
        key = rng.choice(list(new_spec.operator_mix.keys()))
        new_spec.operator_mix[key] += rng.uniform(-delta, delta)
        _renormalize(new_spec.operator_mix)

    new_spec.population_cap = max(
        1, min(MAX_POPULATION_CAP, new_spec.population_cap + rng.choice([-1, 1]))
    )

    strategies = sorted(SELECTION_STRATEGIES)
    current_idx = strategies.index(new_spec.selection_strategy)
    if len(strategies) > 1 and rng.random() < 0.5:
        new_spec.selection_strategy = strategies[(current_idx + 1) % len(strategies)]

    new_spec.validate()
    return new_spec
