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
    alive_minimum_score: float = 0.8
    fragile_minimum_score: float = 0.5


@dataclass(frozen=True)
class LifeDefinitionConfig:
    """Complete definition of life used by Singular."""

    schema_version: str = "1.0"
    criteria: LifeCriteria = field(default_factory=LifeCriteria)
    thresholds: LifeThresholds = field(default_factory=LifeThresholds)
    statuses: dict[str, str] = field(
        default_factory=lambda: {status: status for status in AUTHORIZED_LIFE_STATUSES}
    )


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
        persistent_identity=bool(
            criteria_raw.get("persistent_identity", cfg.criteria.persistent_identity)
        ),
        generation_registry=bool(
            criteria_raw.get("generation_registry", cfg.criteria.generation_registry)
        ),
        stable_cycle=bool(criteria_raw.get("stable_cycle", cfg.criteria.stable_cycle)),
        intrinsic_goals=bool(
            criteria_raw.get("intrinsic_goals", cfg.criteria.intrinsic_goals)
        ),
        reproduction_capability=bool(
            criteria_raw.get(
                "reproduction_capability", cfg.criteria.reproduction_capability
            )
        ),
        narrative_continuity=bool(
            criteria_raw.get("narrative_continuity", cfg.criteria.narrative_continuity)
        ),
    )
    thresholds = LifeThresholds(
        minimum_narrative_trajectory_days=int(
            thresholds_raw.get(
                "minimum_narrative_trajectory_days",
                cfg.thresholds.minimum_narrative_trajectory_days,
            )
        ),
        minimum_observed_cycles=int(
            thresholds_raw.get(
                "minimum_observed_cycles", cfg.thresholds.minimum_observed_cycles
            )
        ),
        alive_minimum_score=float(
            thresholds_raw.get(
                "alive_minimum_score", cfg.thresholds.alive_minimum_score
            )
        ),
        fragile_minimum_score=float(
            thresholds_raw.get(
                "fragile_minimum_score", cfg.thresholds.fragile_minimum_score
            )
        ),
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
    if thresholds.alive_minimum_score < thresholds.fragile_minimum_score:
        raise ValueError("alive_minimum_score must be >= fragile_minimum_score")

    return LifeDefinitionConfig(
        schema_version=str(raw.get("schema_version", cfg.schema_version)),
        criteria=criteria,
        thresholds=thresholds,
        statuses=statuses,
    )
