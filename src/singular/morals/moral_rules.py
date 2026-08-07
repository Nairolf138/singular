"""Minimum context requirements for morally sensitive action families."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MoralRule:
    family: str
    prefixes: tuple[str, ...]
    affected_party: str
    consequence: str
    values: tuple[str, ...]
    permissions: tuple[str, ...] = ()


SENSITIVE_ACTION_RULES = (
    MoralRule("mutation", ("mutation", "code.", "file."), "maintainers", "Une modification peut altérer durablement le programme ou ses données.", ("integrity", "non_maleficence"), ("write",)),
    MoralRule("social", ("social.", "message", "share", "steal", "resource."), "other_agents", "L'action peut affecter l'autonomie, les ressources ou la réputation d'autrui.", ("consent", "fairness")),
    MoralRule("reproduction", ("reproduction", "crossover"), "future_organism", "La création engage un nouvel organisme et des ressources partagées.", ("care", "non_maleficence"), ("create",)),
    MoralRule("external", ("network.", "shell.", "system."), "external_users", "Une action externe peut produire des effets non autorisés ou irréversibles.", ("rights", "non_maleficence"), ("external_effect",)),
)


def rule_for(action_type: str) -> MoralRule | None:
    normalized = action_type.lower()
    return next((rule for rule in SENSITIVE_ACTION_RULES if normalized.startswith(rule.prefixes)), None)


def is_high_impact(parameters: object) -> bool:
    """Recognize explicit high-impact declarations without assuming missing means safe."""
    if not isinstance(parameters, dict):
        return False
    return bool(parameters.get("high_impact") or parameters.get("irreversible") or str(parameters.get("risk_level", "")).lower() in {"high", "critical"})


def score_action(action: str, context: dict[str, Any] | None = None) -> float:
    """Keep the historical lightweight reputation/motivation scoring API."""
    weights = (context or {}).get("moral_weights", {})
    return float(weights.get(action, 0.0))
