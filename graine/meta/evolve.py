from __future__ import annotations

from typing import Dict

from .dsl import MetaSpec, MAX_POPULATION_CAP


def propose_mutation(spec: MetaSpec, delta: float = 0.1) -> MetaSpec:
    """Propose a simple meta-mutation while respecting constitutional limits.

    The mutation deterministically adjusts the first two weights and operator
    mixes while keeping the distributions normalized. The population cap is
    increased by one but clamped to ``MAX_POPULATION_CAP``. The returned
    ``MetaSpec`` is validated before being returned.
    """

    new_spec = MetaSpec(
        weights=dict(spec.weights),
        operator_mix=dict(spec.operator_mix),
        population_cap=spec.population_cap,
    )

    # Mutate weights
    weight_keys = list(new_spec.weights.keys())
    if len(weight_keys) >= 2:
        a, b = weight_keys[:2]
        new_a = min(1.0, max(0.0, new_spec.weights[a] + delta))
        new_spec.weights[a] = new_a
        new_spec.weights[b] = 1.0 - new_a

    # Mutate operator mix
    op_keys = list(new_spec.operator_mix.keys())
    if len(op_keys) >= 2:
        a, b = op_keys[:2]
        new_a = min(1.0, max(0.0, new_spec.operator_mix[a] + delta))
        new_spec.operator_mix[a] = new_a
        new_spec.operator_mix[b] = 1.0 - new_a

    # Increase population cap within limit
    if new_spec.population_cap < MAX_POPULATION_CAP:
        new_spec.population_cap += 1

    new_spec.validate()
    return new_spec
