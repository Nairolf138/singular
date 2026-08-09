"""Configuration driven, multi-objective mutation fitness."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import as_file
from pathlib import Path
from typing import Mapping

from singular.resources import config_resource


def _load_simple_yaml(path: Path) -> dict[str, object]:
    """Parse the mapping-only subset used by the versioned lifecycle file."""
    root: dict[str, object] = {}
    stack: list[tuple[int, dict[str, object]]] = [(-1, root)]
    for source_line in path.read_text(encoding="utf-8").splitlines():
        line = source_line.split("#", 1)[0].rstrip()
        if not line.strip() or ":" not in line:
            continue
        indent = len(line) - len(line.lstrip())
        key, value = line.strip().split(":", 1)
        while stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]
        if not value.strip():
            child: dict[str, object] = {}
            parent[key] = child
            stack.append((indent, child))
            continue
        scalar = value.strip()
        try:
            parsed: object = float(scalar) if "." in scalar else int(scalar)
        except ValueError:
            parsed = (
                scalar.lower() == "true"
                if scalar.lower() in {"true", "false"}
                else scalar
            )
        parent[key] = parsed
    return root


COMPONENTS = (
    "functional_gain",
    "health",
    "vital_risk",
    "resources",
    "sandbox_stability",
    "cost",
    "quest_progress",
    "identity_continuity",
    "useful_skills_retention",
)


@dataclass(frozen=True)
class LifecycleFitnessConfig:
    weights: dict[str, float]
    minimum_observations: int
    minimum_fitness_gain: float
    maximum_vital_regression: float


@dataclass(frozen=True)
class FitnessDecision:
    accepted: bool
    useful: bool
    viable: bool
    fitness_before: float
    fitness_after: float
    components_before: dict[str, float]
    components_after: dict[str, float]
    rejection_reasons: tuple[str, ...]
    observations: int

    def to_dict(self) -> dict[str, object]:
        return {
            "accepted": self.accepted,
            "useful": self.useful,
            "durably_viable": self.viable,
            "fitness_before": self.fitness_before,
            "fitness_after": self.fitness_after,
            "fitness_components_before": self.components_before,
            "fitness_components": self.components_after,
            "fitness_delta": self.fitness_after - self.fitness_before,
            "rejection_reasons": list(self.rejection_reasons),
            "observation_window": self.observations,
        }


def load_lifecycle_fitness_config(path: Path | None = None) -> LifecycleFitnessConfig:
    if path is None:
        resource = config_resource("lifecycle.yaml")
        with as_file(resource) as resolved:
            raw = _load_simple_yaml(resolved)
    else:
        raw = _load_simple_yaml(path)
    section = raw.get("mutation_fitness", {})
    weights = {
        name: float(section.get("weights", {}).get(name, 0.0)) for name in COMPONENTS
    }
    observation = section.get("observation", {})
    thresholds = section.get("thresholds", {})
    return LifecycleFitnessConfig(
        weights=weights,
        minimum_observations=max(1, int(observation.get("minimum_samples", 1))),
        minimum_fitness_gain=float(thresholds.get("minimum_fitness_gain", 0.0)),
        maximum_vital_regression=float(thresholds.get("maximum_vital_regression", 0.1)),
    )


def evaluate_mutation_fitness(
    before: Mapping[str, float],
    after: Mapping[str, float],
    config: LifecycleFitnessConfig,
    *,
    observations: int,
) -> FitnessDecision:
    """Compare a candidate with its immutable pre-mutation snapshot.

    All components use the convention "higher is better"; ``vital_risk`` and
    ``cost`` are therefore assigned negative weights in configuration.
    """
    b = {name: float(before.get(name, 0.0)) for name in COMPONENTS}
    a = {name: float(after.get(name, 0.0)) for name in COMPONENTS}
    score_before = sum(config.weights[n] * b[n] for n in COMPONENTS)
    score_after = sum(config.weights[n] * a[n] for n in COMPONENTS)
    vital_regression = max(0.0, b["health"] - a["health"]) + max(
        0.0, a["vital_risk"] - b["vital_risk"]
    )
    reasons: list[str] = []
    if observations < config.minimum_observations:
        reasons.append("observation_window_too_short")
    if vital_regression > config.maximum_vital_regression:
        reasons.append("vital_regression_threshold_exceeded")
    delta = score_after - score_before
    if delta < config.minimum_fitness_gain:
        reasons.append("combined_fitness_below_threshold")
    viable = vital_regression <= config.maximum_vital_regression
    return FitnessDecision(
        accepted=not reasons,
        useful=a["functional_gain"] > b["functional_gain"],
        viable=viable,
        fitness_before=score_before,
        fitness_after=score_after,
        components_before=b,
        components_after=a,
        rejection_reasons=tuple(reasons),
        observations=observations,
    )
