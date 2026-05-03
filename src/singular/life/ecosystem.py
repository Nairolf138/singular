from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class ArchetypeProfile:
    name: str
    capabilities: tuple[str, ...]
    strategy: str
    energy_bias: float = 0.0
    resource_bias: float = 0.0
    cooperation_bias: float = 0.0
    competition_bias: float = 0.0


ARCHETYPES: dict[str, ArchetypeProfile] = {
    "explorer": ArchetypeProfile(
        name="explorer",
        capabilities=("mutation_speed", "discovery"),
        strategy="high-variance exploration and rapid adaptation",
        energy_bias=-0.05,
        resource_bias=0.03,
        cooperation_bias=0.1,
        competition_bias=0.0,
    ),
    "stabilizer": ArchetypeProfile(
        name="stabilizer",
        capabilities=("efficiency", "risk_control"),
        strategy="conservative mutation and consistency",
        energy_bias=0.03,
        resource_bias=0.02,
        cooperation_bias=0.15,
        competition_bias=-0.05,
    ),
    "parasite": ArchetypeProfile(
        name="parasite",
        capabilities=("opportunism", "resource_capture"),
        strategy="extract resources from ecosystem asymmetries",
        energy_bias=0.02,
        resource_bias=0.08,
        cooperation_bias=-0.2,
        competition_bias=0.2,
    ),
    "guardian": ArchetypeProfile(
        name="guardian",
        capabilities=("defense", "collective_recovery"),
        strategy="protect commons and absorb shocks",
        energy_bias=0.04,
        resource_bias=-0.01,
        cooperation_bias=0.25,
        competition_bias=-0.1,
    ),
}


@dataclass
class EcosystemRulesConfig:
    schema_version: int = 1
    mode: str = "production"
    resource_competition_unit: float = 1.0
    passive_energy_decay: float = 0.05
    passive_resource_decay: float = 0.02
    crossover_interval: int = 50
    cooperation_probability: float = 0.2
    competition_bid_ceiling: float = 5.0
    reputation_action_weights: dict[str, float] = field(
        default_factory=lambda: {"share": 0.2, "steal": -0.2}
    )

    @classmethod
    def from_file(cls, path: Path) -> "EcosystemRulesConfig":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            schema_version=int(payload.get("schema_version", 1)),
            mode=str(payload.get("mode", "production")),
            resource_competition_unit=float(payload.get("resource_competition_unit", 1.0)),
            passive_energy_decay=float(payload.get("passive_energy_decay", 0.05)),
            passive_resource_decay=float(payload.get("passive_resource_decay", 0.02)),
            crossover_interval=int(payload.get("crossover_interval", 50)),
            cooperation_probability=float(payload.get("cooperation_probability", 0.2)),
            competition_bid_ceiling=float(payload.get("competition_bid_ceiling", 5.0)),
            reputation_action_weights=dict(payload.get("reputation_action_weights", {"share": 0.2, "steal": -0.2})),
        )


@dataclass(frozen=True)
class GlobalEvent:
    event_type: str
    intensity: float
    duration_ticks: int
    description: str


def draw_global_event(rng: random.Random) -> GlobalEvent:
    templates = [
        ("resource_crisis", "global resource scarcity"),
        ("governance_shift", "governance priorities shifted"),
        ("simulated_catastrophe", "systemic catastrophe simulation"),
    ]
    event_type, desc = rng.choice(templates)
    return GlobalEvent(event_type=event_type, intensity=rng.uniform(0.2, 0.9), duration_ticks=rng.randint(2, 6), description=desc)


def compute_population_metrics(before: Mapping[str, tuple[float, float]], after: Mapping[str, tuple[float, float]], ticks_elapsed: int) -> dict[str, float]:
    if not before or not after:
        return {"resilience": 0.0, "diversity": 0.0, "recovery_time": float(max(ticks_elapsed, 0))}
    before_total = sum(max(0.0, e + r) for e, r in before.values())
    after_total = sum(max(0.0, e + r) for e, r in after.values())
    resilience = 0.0 if before_total <= 0 else min(after_total / before_total, 2.0)
    alive = sum(1 for e, r in after.values() if (e + r) > 0.2)
    diversity = alive / max(len(after), 1)
    return {
        "resilience": round(resilience, 4),
        "diversity": round(diversity, 4),
        "recovery_time": float(max(ticks_elapsed, 0)),
    }
