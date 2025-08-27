from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from graine.evolver.dsl import OPERATOR_NAMES


class MetaValidationError(ValueError):
    """Raised when a meta configuration is invalid."""


MAX_POPULATION_CAP = 100
_WEIGHT_TOLERANCE = 1e-6


@dataclass
class MetaSpec:
    """Specification for meta-level evolutionary settings."""

    weights: Dict[str, float] = field(default_factory=dict)
    operator_mix: Dict[str, float] = field(default_factory=dict)
    population_cap: int = 0

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "MetaSpec":
        return cls(
            weights=dict(data.get("weights", {})),
            operator_mix=dict(data.get("operator_mix", {})),
            population_cap=int(data.get("population_cap", 0)),
        )

    def validate(self) -> bool:
        # Validate weights
        if not self.weights:
            raise MetaValidationError("Weights must be provided")
        total = sum(self.weights.values())
        if any(w < 0 or w > 1 for w in self.weights.values()) or abs(total - 1.0) > _WEIGHT_TOLERANCE:
            raise MetaValidationError("Weights must be within [0,1] and sum to 1")

        # Validate operator mix
        if not self.operator_mix:
            raise MetaValidationError("Operator mix must be provided")
        unknown = [op for op in self.operator_mix if op not in OPERATOR_NAMES]
        if unknown:
            raise MetaValidationError(f"Unknown operator in mix: {unknown[0]}")
        op_total = sum(self.operator_mix.values())
        if any(v < 0 for v in self.operator_mix.values()) or abs(op_total - 1.0) > _WEIGHT_TOLERANCE:
            raise MetaValidationError("Operator mix must be non-negative and sum to 1")

        # Validate population cap
        if not (0 < self.population_cap <= MAX_POPULATION_CAP):
            raise MetaValidationError("Population cap exceeds constitutional limit")
        return True
