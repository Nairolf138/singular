from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from singular.environment.sim_world import WORLD_ACTION_NAMES, world_action_to_effect


@dataclass(slots=True)
class EffectResult:
    action: str
    success: bool
    energy_delta: float = 0.0
    health_delta: float = 0.0
    mortality_delta: float = 0.0
    world_delta: dict[str, float] = field(default_factory=dict)
    delayed_penalties: list[dict[str, float | int]] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _scaled_symbolic_delta(effect: dict[str, object], resource: str) -> float:
    produced = effect.get("produce_resources", {})
    consumed = effect.get("consume_resources", {})
    if not isinstance(produced, dict) or not isinstance(consumed, dict):
        return 0.0
    produced_symbolic = produced.get("symbolic", {})
    consumed_symbolic = consumed.get("symbolic", {})
    if not isinstance(produced_symbolic, dict) or not isinstance(
        consumed_symbolic, dict
    ):
        return 0.0
    return float(produced_symbolic.get(resource, 0.0)) - float(
        consumed_symbolic.get(resource, 0.0)
    )


def _perform_world_action(action: str, payload: dict[str, object]) -> EffectResult:
    risk = float(payload.get("risk", 0.0))
    rarity_pressure = float(payload.get("rarity_pressure", 0.0))
    success_bias = float(payload.get("success_bias", 0.0))
    competition_pressure = float(payload.get("competition_pressure", rarity_pressure))
    effect = world_action_to_effect(action, payload)
    confidence = _clamp(0.62 + success_bias - (risk * 0.18) - (rarity_pressure * 0.08))
    energy_delta = _scaled_symbolic_delta(effect, "energy") / 10.0
    reputation_delta = _scaled_symbolic_delta(effect, "local_reputation") / 100.0
    food_delta = _scaled_symbolic_delta(effect, "food_symbolic") / 100.0
    health_delta = float(effect.get("health_delta", 0.0)) * confidence
    world_delta = {
        "rarity": -food_delta,
        "risks": -0.03 * confidence if action == "avoid_threat" else 0.01 * risk,
        "reputation": reputation_delta,
        "opportunities": 0.02 * confidence,
        "competition": (
            -0.02 * confidence
            if action in {"cooperate", "share_resource"}
            else 0.02 * competition_pressure
        ),
    }
    delayed_penalties: list[dict[str, float | int]] = []
    if action in {"forage", "compete", "move"}:
        delayed_penalties.append(
            {"ticks": 2, "energy_delta": -0.05 * max(0.0, 1.0 - confidence)}
        )
    return EffectResult(
        action,
        confidence >= 0.45,
        energy_delta=energy_delta,
        health_delta=health_delta,
        mortality_delta=-0.01 * confidence if action == "avoid_threat" else 0.0,
        world_delta=world_delta,
        delayed_penalties=delayed_penalties,
        metadata={
            "confidence": confidence,
            "world_action_effect": effect,
        },
    )


def perform_action(
    action: str, context: Mapping[str, object] | None = None
) -> EffectResult:
    payload = dict(context or {})
    risk = float(payload.get("risk", 0.0))
    rarity_pressure = float(payload.get("rarity_pressure", 0.0))
    success_bias = float(payload.get("success_bias", 0.0))
    if action in WORLD_ACTION_NAMES:
        return _perform_world_action(action, payload)
    if action == "resource_management":
        eff = _clamp(0.6 + success_bias - rarity_pressure * 0.1)
        return EffectResult(
            action,
            eff >= 0.5,
            energy_delta=0.2 * eff,
            health_delta=0.1 * eff,
            world_delta={"rarity": -0.05 * eff, "opportunities": 0.03 * eff},
            delayed_penalties=[{"ticks": 3, "energy_delta": -0.1 * (1.0 - eff)}],
            metadata={"efficiency": eff},
        )
    if action == "structured_user_interaction":
        q = _clamp(0.5 + success_bias - risk * 0.2)
        return EffectResult(
            action,
            q >= 0.45,
            energy_delta=0.05,
            health_delta=0.08 * q,
            world_delta={"reputation": 0.06 * q, "opportunities": 0.02 * q},
            delayed_penalties=[
                {"ticks": 2, "mortality_delta": 0.01 * max(0.0, risk - q)}
            ],
            metadata={"interaction_quality": q},
        )
    impact = _clamp(0.55 + success_bias - risk * 0.15)
    return EffectResult(
        action,
        impact >= 0.5,
        energy_delta=0.1 * impact,
        health_delta=0.05 * impact,
        mortality_delta=-0.01 * impact,
        world_delta={"risks": -0.04 * impact, "opportunities": 0.04 * impact},
        delayed_penalties=[{"ticks": 4, "health_delta": -0.08 * (1.0 - impact)}],
        metadata={"world_impact": impact},
    )
