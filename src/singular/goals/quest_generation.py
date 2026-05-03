"""Quest generation heuristics driven by internal and external pressures."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Literal

Origin = Literal["intrinsic", "external"]


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class GeneratedQuest:
    """Minimal generated quest payload.

    The payload is intentionally compact so it can be persisted or transformed
    into a richer runtime representation by the caller.
    """

    name: str
    objective: str
    rationale: str
    origin: Origin
    priority: float

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["priority"] = round(float(payload["priority"]), 3)
        return payload


def generate_quests(
    *,
    psyche_traits: Mapping[str, Any] | None,
    outcomes_history: Mapping[str, Any] | None,
    value_performance_tension: Mapping[str, Any] | float | None,
    world_state: Mapping[str, Any] | None,
    resources: Mapping[str, Any] | None,
    surprise_signals: Mapping[str, Any] | None = None,
) -> list[GeneratedQuest]:
    """Generate candidate quests from psyche, history, tensions, and world/resources."""

    traits = psyche_traits or {}
    history = outcomes_history or {}
    world = world_state or {}
    stock = resources or {}

    resilience = _clamp(_as_float(traits.get("resilience", 0.5), default=0.5))
    optimism = _clamp(_as_float(traits.get("optimism", 0.5), default=0.5))
    curiosity = _clamp(_as_float(traits.get("curiosity", 0.5), default=0.5))

    recent_successes = _as_float(history.get("recent_successes", 0.0), default=0.0)
    recent_failures = _as_float(history.get("recent_failures", 0.0), default=0.0)

    if isinstance(value_performance_tension, Mapping):
        tension = _clamp(_as_float(value_performance_tension.get("score", 0.0), default=0.0))
    else:
        tension = _clamp(_as_float(value_performance_tension, default=0.0))

    energy = _clamp(_as_float(stock.get("energy", 50.0), default=50.0) / 100.0)
    food = _clamp(_as_float(stock.get("food", 50.0), default=50.0) / 100.0)
    warmth = _clamp(_as_float(stock.get("warmth", 50.0), default=50.0) / 100.0)

    delayed_crisis = _clamp(_as_float(world.get("delayed_crisis_pressure", 0.0), default=0.0))
    opportunity = _clamp(_as_float(world.get("opportunity_pressure", 0.0), default=0.0))

    generated: list[GeneratedQuest] = []
    surprise = surprise_signals or {}
    surprise_level = _clamp(_as_float(surprise.get("surprise", 0.0), default=0.0))
    frustration_level = _clamp(_as_float(surprise.get("frustration", 0.0), default=0.0))
    curiosity_spike = _clamp(_as_float(surprise.get("curiosity", curiosity), default=curiosity))
    repeated_operator_failures = _clamp(_as_float(surprise.get("operator_family_failure_pressure", 0.0), default=0.0))

    if tension >= 0.45:
        generated.append(
            GeneratedQuest(
                name="realign_values_vs_performance",
                objective="Réduire la friction entre valeurs et rendement.",
                rationale="Tension valeurs/performance élevée.",
                origin="intrinsic",
                priority=_clamp(0.45 + tension * 0.5),
            )
        )

    failure_pressure = _clamp((recent_failures - recent_successes) / 5.0)
    if failure_pressure > 0.1:
        generated.append(
            GeneratedQuest(
                name="recover_execution_reliability",
                objective="Restaurer la stabilité d'exécution après une série d'échecs.",
                rationale="Historique récent orienté vers l'échec.",
                origin="intrinsic",
                priority=_clamp(0.4 + failure_pressure * 0.5 + (1.0 - resilience) * 0.2),
            )
        )

    internal_quest_pressure = _clamp(
        (surprise_level * 0.3)
        + (frustration_level * 0.35)
        + (curiosity_spike * 0.15)
        + (repeated_operator_failures * 0.4)
    )
    if internal_quest_pressure >= 0.3:
        generated.append(
            GeneratedQuest(
                name="probe_operator_failure_cluster",
                objective="Diagnostiquer les échecs récurrents d'une famille d'opérateurs.",
                rationale="Signaux internes surprise/frustration/curiosité indiquent un blocage durable.",
                origin="intrinsic",
                priority=_clamp(0.4 + internal_quest_pressure * 0.55),
            )
        )

    resource_pressure = _clamp(1.0 - ((energy + food + warmth) / 3.0))
    if resource_pressure >= 0.35:
        generated.append(
            GeneratedQuest(
                name="stabilize_critical_resources",
                objective="Sécuriser énergie, nourriture et chaleur.",
                rationale="Niveau de ressources en baisse.",
                origin="external",
                priority=_clamp(0.5 + resource_pressure * 0.4),
            )
        )

    if delayed_crisis >= 0.4:
        generated.append(
            GeneratedQuest(
                name="anticipate_world_crisis",
                objective="Anticiper les crises différées du monde.",
                rationale="Signaux de crise environnementale retardée détectés.",
                origin="external",
                priority=_clamp(0.5 + delayed_crisis * 0.4 + (1.0 - optimism) * 0.2),
            )
        )

    if opportunity >= 0.4 and curiosity >= 0.45:
        generated.append(
            GeneratedQuest(
                name="capture_emergent_opportunity",
                objective="Exploiter une opportunité externe émergente.",
                rationale="Fenêtre d'opportunité détectée avec curiosité suffisante.",
                origin="external",
                priority=_clamp(0.35 + opportunity * 0.4 + curiosity * 0.2),
            )
        )

    generated.sort(key=lambda quest: quest.priority, reverse=True)
    return generated
