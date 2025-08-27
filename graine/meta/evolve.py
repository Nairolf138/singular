from __future__ import annotations

from random import Random
from typing import Dict

from .dsl import MetaSpec, MAX_POPULATION_CAP


def _renormalize(dist: Dict[str, float]) -> None:
    """Scale the values in ``dist`` so they sum to ``1.0``.

    The operation happens in-place and ignores empty dictionaries. Negative
    values are clamped to ``0`` before normalisation to guarantee a valid
    probability distribution.
    """

    if not dist:
        return
    total = 0.0
    for k, v in dist.items():
        if v < 0:
            v = 0.0
        dist[k] = v
        total += v
    if total == 0:
        # Evenly distribute if everything was clamped to zero
        share = 1.0 / len(dist)
        for k in dist:
            dist[k] = share
        return
    for k in dist:
        dist[k] /= total


def propose_mutation(
    spec: MetaSpec, delta: float = 0.1, rng: Random | None = None
) -> MetaSpec:
    """Propose a meta-mutation compliant with :mod:`graine.meta.dsl`.

    The mutation adjusts a random objective weight and operator frequency while
    keeping the respective distributions normalised.  The population cap is
    incremented or decremented by one without exceeding
    ``MAX_POPULATION_CAP``.  All other constitutional parameters remain
    unchanged.  The resulting :class:`MetaSpec` is validated prior to being
    returned.
    """

    rng = rng or Random()

    new_spec = MetaSpec(
        weights=dict(spec.weights),
        operator_mix=dict(spec.operator_mix),
        population_cap=spec.population_cap,
        selection_strategy=spec.selection_strategy,
        diff_max=spec.diff_max,
        forbidden=list(spec.forbidden),
    )

    # Mutate weights by tweaking a random entry and re-normalising
    if len(new_spec.weights) >= 1:
        key = rng.choice(list(new_spec.weights.keys()))
        new_spec.weights[key] += rng.uniform(-delta, delta)
        _renormalize(new_spec.weights)

    # Mutate operator mix similarly
    if len(new_spec.operator_mix) >= 1:
        key = rng.choice(list(new_spec.operator_mix.keys()))
        new_spec.operator_mix[key] += rng.uniform(-delta, delta)
        _renormalize(new_spec.operator_mix)

    # Adjust population cap but respect constitutional ceiling
    pop_change = rng.choice([-1, 1])
    new_pop = new_spec.population_cap + pop_change
    new_spec.population_cap = max(1, min(MAX_POPULATION_CAP, new_pop))

    new_spec.validate()
    return new_spec
