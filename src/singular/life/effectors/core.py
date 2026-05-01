from __future__ import annotations
from dataclasses import dataclass, field
from typing import Mapping

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

def perform_action(action: str, context: Mapping[str, object] | None = None) -> EffectResult:
    payload = dict(context or {})
    risk = float(payload.get('risk', 0.0))
    rarity_pressure = float(payload.get('rarity_pressure', 0.0))
    success_bias = float(payload.get('success_bias', 0.0))
    if action == 'resource_management':
        eff = max(0.0, min(1.0, 0.6 + success_bias - rarity_pressure * 0.1))
        return EffectResult(action, eff >= 0.5, energy_delta=0.2*eff, health_delta=0.1*eff, world_delta={'rarity': -0.05*eff, 'opportunities': 0.03*eff}, delayed_penalties=[{'ticks': 3, 'energy_delta': -0.1*(1.0-eff)}], metadata={'efficiency': eff})
    if action == 'structured_user_interaction':
        q = max(0.0, min(1.0, 0.5 + success_bias - risk * 0.2))
        return EffectResult(action, q >= 0.45, energy_delta=0.05, health_delta=0.08*q, world_delta={'reputation': 0.06*q, 'opportunities': 0.02*q}, delayed_penalties=[{'ticks': 2, 'mortality_delta': 0.01*max(0.0, risk-q)}], metadata={'interaction_quality': q})
    impact = max(0.0, min(1.0, 0.55 + success_bias - risk * 0.15))
    return EffectResult(action, impact >= 0.5, energy_delta=0.1*impact, health_delta=0.05*impact, mortality_delta=-0.01*impact, world_delta={'risks': -0.04*impact, 'opportunities': 0.04*impact}, delayed_penalties=[{'ticks': 4, 'health_delta': -0.08*(1.0-impact)}], metadata={'world_impact': impact})
