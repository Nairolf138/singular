from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Any, cast

from graine.evolver.dsl import OPERATOR_NAMES
from graine.kernel.verifier import DIFF_LIMIT


class MetaValidationError(ValueError):
    """Raised when a meta configuration is invalid."""


MAX_POPULATION_CAP = 100
_WEIGHT_TOLERANCE = 1e-6

SELECTION_STRATEGIES = {"elitism"}

# Minimal JSON schema describing a meta specification
META_SCHEMA: Dict[str, Any] = {
    "required": ["weights", "operator_mix", "population_cap", "selection_strategy"],
    "properties": {
        "weights": {"type": "object"},
        "operator_mix": {"type": "object"},
        "population_cap": {"type": "integer"},
        "selection_strategy": {"type": "string"},
        "diff_max": {"type": "integer"},
        "forbidden": {"type": "array"},
    },
}


@dataclass
class MetaSpec:
    """Specification for meta-level evolutionary settings."""

    weights: Dict[str, float] = field(default_factory=dict)
    operator_mix: Dict[str, float] = field(default_factory=dict)
    population_cap: int = 0
    selection_strategy: str = "elitism"
    diff_max: int = DIFF_LIMIT
    forbidden: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "MetaSpec":
        weights_raw = data.get("weights", {})
        operator_mix_raw = data.get("operator_mix", {})
        forbidden_raw = data.get("forbidden", [])

        weights = cast(Dict[str, float], weights_raw if isinstance(weights_raw, dict) else {})
        operator_mix = cast(
            Dict[str, float],
            operator_mix_raw if isinstance(operator_mix_raw, dict) else {},
        )
        forbidden = cast(List[str], forbidden_raw if isinstance(forbidden_raw, list) else [])

        population_cap_raw = data.get("population_cap", 0)
        diff_max_raw = data.get("diff_max", DIFF_LIMIT)

        return cls(
            weights=weights,
            operator_mix=operator_mix,
            population_cap=int(population_cap_raw) if isinstance(population_cap_raw, (int, str)) else 0,
            selection_strategy=str(data.get("selection_strategy", "elitism")),
            diff_max=int(diff_max_raw) if isinstance(diff_max_raw, (int, str)) else DIFF_LIMIT,
            forbidden=forbidden,
        )

    def validate(self) -> bool:
        # Validate weights
        if not self.weights:
            raise MetaValidationError("Weights must be provided")
        total = sum(self.weights.values())
        if (
            any(w < 0 or w > 1 for w in self.weights.values())
            or abs(total - 1.0) > _WEIGHT_TOLERANCE
        ):
            raise MetaValidationError("Weights must be within [0,1] and sum to 1")

        # Validate operator mix
        if not self.operator_mix:
            raise MetaValidationError("Operator mix must be provided")
        unknown = [op for op in self.operator_mix if op not in OPERATOR_NAMES]
        if unknown:
            raise MetaValidationError(f"Unknown operator in mix: {unknown[0]}")
        op_total = sum(self.operator_mix.values())
        if (
            any(v < 0 for v in self.operator_mix.values())
            or abs(op_total - 1.0) > _WEIGHT_TOLERANCE
        ):
            raise MetaValidationError("Operator mix must be non-negative and sum to 1")

        # Validate population cap
        if not (0 < self.population_cap <= MAX_POPULATION_CAP):
            raise MetaValidationError("Population cap exceeds constitutional limit")

        # Validate selection strategy
        if self.selection_strategy not in SELECTION_STRATEGIES:
            raise MetaValidationError("Unknown selection strategy")

        # Validate constitutional limits
        if self.diff_max > DIFF_LIMIT:
            raise MetaValidationError("diff_max exceeds constitutional limit")
        if self.forbidden:
            raise MetaValidationError("Cannot relax constitutional forbiddens")
        return True
