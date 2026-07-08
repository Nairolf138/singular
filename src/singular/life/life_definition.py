"""Life definition configuration helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from singular.life.life_status import AUTHORIZED_LIFE_STATUSES
from singular.orchestrator.lifecycle_clock import _load_simple_yaml

DEFAULT_LIFECYCLE_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "configs" / "lifecycle.yaml"
)
DEFAULT_LIFE_DEFINITION_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "configs" / "life_definition.yaml"
)


@dataclass(frozen=True)
class LifeCriteria:
    """Criteria used to evaluate whether an organism should be considered alive."""

    persistent_identity: bool = True
    generation_registry: bool = True
    stable_cycle: bool = True
    intrinsic_goals: bool = True
    reproduction_capability: bool = True
    narrative_continuity: bool = True


@dataclass(frozen=True)
class LifeThresholds:
    """Configurable thresholds for life status evaluation."""

    minimum_narrative_trajectory_days: int = 7
    minimum_observed_cycles: int = 3
    maximum_cycle_anomalies: int = 1
    alive_minimum_score: float = 0.8
    fragile_minimum_score: float = 0.5
    dying_degradation_minimum_score: float = 0.4


@dataclass(frozen=True)
class WeightedCriterion:
    """Weighted contribution to the life qualification score."""

    points: float
    required_for_alive: bool = True


@dataclass(frozen=True)
class LifeWeightedScore:
    """Weighted scoring model for life status evaluation."""

    total_points: float = 100.0
    criteria: dict[str, WeightedCriterion] = field(
        default_factory=lambda: {
            "persistent_identity": WeightedCriterion(20.0, True),
            "generation_registry": WeightedCriterion(15.0, True),
            "stable_cycle": WeightedCriterion(20.0, True),
            "intrinsic_goals": WeightedCriterion(20.0, True),
            "reproduction_capability": WeightedCriterion(10.0, False),
            "narrative_continuity": WeightedCriterion(15.0, True),
        }
    )


@dataclass(frozen=True)
class LifeDefinitionConfig:
    """Complete definition of life used by Singular."""

    schema_version: str = "1.0"
    criteria: LifeCriteria = field(default_factory=LifeCriteria)
    thresholds: LifeThresholds = field(default_factory=LifeThresholds)
    weighted_score: LifeWeightedScore = field(default_factory=LifeWeightedScore)
    statuses: dict[str, str] = field(
        default_factory=lambda: {status: status for status in AUTHORIZED_LIFE_STATUSES}
    )


def _require_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    raise ValueError(f"{field_name} must be a boolean")


def _require_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc


def _require_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a number")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number") from exc


def _load_raw_life_definition(path: Path | None) -> dict[str, Any]:
    if path is not None:
        if not path.exists():
            return {}
        raw = _load_simple_yaml(path)
        section = raw.get("life_definition")
        return section if isinstance(section, dict) else raw

    if DEFAULT_LIFE_DEFINITION_CONFIG_PATH.exists():
        raw = _load_simple_yaml(DEFAULT_LIFE_DEFINITION_CONFIG_PATH)
        section = raw.get("life_definition")
        return section if isinstance(section, dict) else raw

    if DEFAULT_LIFECYCLE_CONFIG_PATH.exists():
        raw = _load_simple_yaml(DEFAULT_LIFECYCLE_CONFIG_PATH)
        section = raw.get("life_definition")
        return section if isinstance(section, dict) else {}

    return {}


def load_life_definition_config(path: Path | None = None) -> LifeDefinitionConfig:
    """Load the life definition config, returning defaults when absent.

    The loader accepts either a dedicated ``configs/life_definition.yaml`` file or a
    ``life_definition`` section embedded in ``configs/lifecycle.yaml``. Missing files
    and missing keys are intentionally backward-compatible with older deployments.
    """

    cfg = LifeDefinitionConfig()
    raw = _load_raw_life_definition(path)
    if not raw:
        return cfg

    criteria_raw = (
        raw.get("criteria", {}) if isinstance(raw.get("criteria", {}), dict) else {}
    )
    thresholds_raw = (
        raw.get("thresholds", {}) if isinstance(raw.get("thresholds", {}), dict) else {}
    )
    statuses_raw = (
        raw.get("statuses", {}) if isinstance(raw.get("statuses", {}), dict) else {}
    )

    criteria = LifeCriteria(
        persistent_identity=_require_bool(
            criteria_raw.get("persistent_identity", cfg.criteria.persistent_identity),
            "criteria.persistent_identity",
        ),
        generation_registry=_require_bool(
            criteria_raw.get("generation_registry", cfg.criteria.generation_registry),
            "criteria.generation_registry",
        ),
        stable_cycle=_require_bool(
            criteria_raw.get("stable_cycle", cfg.criteria.stable_cycle),
            "criteria.stable_cycle",
        ),
        intrinsic_goals=_require_bool(
            criteria_raw.get("intrinsic_goals", cfg.criteria.intrinsic_goals),
            "criteria.intrinsic_goals",
        ),
        reproduction_capability=_require_bool(
            criteria_raw.get(
                "reproduction_capability", cfg.criteria.reproduction_capability
            ),
            "criteria.reproduction_capability",
        ),
        narrative_continuity=_require_bool(
            criteria_raw.get("narrative_continuity", cfg.criteria.narrative_continuity),
            "criteria.narrative_continuity",
        ),
    )
    thresholds = LifeThresholds(
        minimum_narrative_trajectory_days=_require_int(
            thresholds_raw.get(
                "minimum_narrative_trajectory_days",
                cfg.thresholds.minimum_narrative_trajectory_days,
            ),
            "thresholds.minimum_narrative_trajectory_days",
        ),
        minimum_observed_cycles=_require_int(
            thresholds_raw.get(
                "minimum_observed_cycles", cfg.thresholds.minimum_observed_cycles
            ),
            "thresholds.minimum_observed_cycles",
        ),
        maximum_cycle_anomalies=_require_int(
            thresholds_raw.get(
                "maximum_cycle_anomalies", cfg.thresholds.maximum_cycle_anomalies
            ),
            "thresholds.maximum_cycle_anomalies",
        ),
        alive_minimum_score=_require_float(
            thresholds_raw.get(
                "alive_minimum_score", cfg.thresholds.alive_minimum_score
            ),
            "thresholds.alive_minimum_score",
        ),
        fragile_minimum_score=_require_float(
            thresholds_raw.get(
                "fragile_minimum_score", cfg.thresholds.fragile_minimum_score
            ),
            "thresholds.fragile_minimum_score",
        ),
        dying_degradation_minimum_score=_require_float(
            thresholds_raw.get(
                "dying_degradation_minimum_score",
                cfg.thresholds.dying_degradation_minimum_score,
            ),
            "thresholds.dying_degradation_minimum_score",
        ),
    )
    weighted_raw = (
        raw.get("weighted_score", {})
        if isinstance(raw.get("weighted_score", {}), dict)
        else {}
    )
    weighted_criteria_raw = (
        weighted_raw.get("criteria", {})
        if isinstance(weighted_raw.get("criteria", {}), dict)
        else {}
    )
    weighted_defaults = cfg.weighted_score.criteria
    aliases = {"continuous_intrinsic_goals": "intrinsic_goals"}
    weighted_criteria = dict(weighted_defaults)
    for raw_name, value in weighted_criteria_raw.items():
        name = aliases.get(str(raw_name), str(raw_name))
        if name not in weighted_defaults or not isinstance(value, dict):
            continue
        weighted_criteria[name] = WeightedCriterion(
            points=_require_float(
                value.get("points", weighted_defaults[name].points),
                f"weighted_score.criteria.{name}.points",
            ),
            required_for_alive=_require_bool(
                value.get(
                    "required_for_alive",
                    weighted_defaults[name].required_for_alive,
                ),
                f"weighted_score.criteria.{name}.required_for_alive",
            ),
        )
    weighted_score = LifeWeightedScore(
        total_points=_require_float(
            weighted_raw.get("total_points", cfg.weighted_score.total_points),
            "weighted_score.total_points",
        ),
        criteria=weighted_criteria,
    )
    unknown = sorted(set(statuses_raw) - set(AUTHORIZED_LIFE_STATUSES))
    if unknown:
        raise ValueError(
            f"life statuses contain unauthorized keys: {', '.join(unknown)}"
        )

    statuses = dict(cfg.statuses)
    for name in AUTHORIZED_LIFE_STATUSES:
        value = statuses_raw.get(name, statuses[name])
        statuses[name] = str(value)

    missing = [status for status in AUTHORIZED_LIFE_STATUSES if status not in statuses]
    if missing:
        raise ValueError(f"life statuses missing required keys: {', '.join(missing)}")
    if thresholds.minimum_narrative_trajectory_days < 0:
        raise ValueError("minimum_narrative_trajectory_days must be >= 0")
    if thresholds.minimum_observed_cycles < 0:
        raise ValueError("minimum_observed_cycles must be >= 0")
    if thresholds.maximum_cycle_anomalies < 0:
        raise ValueError("maximum_cycle_anomalies must be >= 0")
    if thresholds.alive_minimum_score < thresholds.fragile_minimum_score:
        raise ValueError("alive_minimum_score must be >= fragile_minimum_score")
    if weighted_score.total_points <= 0:
        raise ValueError("weighted_score.total_points must be > 0")

    return LifeDefinitionConfig(
        schema_version=str(raw.get("schema_version", cfg.schema_version)),
        criteria=criteria,
        thresholds=thresholds,
        weighted_score=weighted_score,
        statuses=statuses,
    )
