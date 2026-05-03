from __future__ import annotations

from dataclasses import dataclass

from singular.resource_manager import ResourceManager


@dataclass(frozen=True)
class RewardContribution:
    resolved_quests: int = 0
    tech_debt_delta: float = 0.0
    user_satisfaction: float = 0.0


def apply_rewards(resource_manager: ResourceManager, contribution: RewardContribution) -> None:
    """Convert measurable contributions into homeostatic gains."""
    if contribution.resolved_quests > 0:
        resource_manager.add_food(min(12.0, contribution.resolved_quests * 1.5))
        resource_manager.regenerate_energy(min(10.0, contribution.resolved_quests * 1.0))
    if contribution.tech_debt_delta < 0:
        reduction = min(8.0, abs(contribution.tech_debt_delta) * 2.0)
        resource_manager.regenerate_energy(reduction)
        resource_manager.relational_debt = max(0.0, resource_manager.relational_debt - reduction * 0.5)
    if contribution.user_satisfaction > 0:
        resource_manager.add_warmth(min(10.0, contribution.user_satisfaction * 8.0))
    resource_manager._clamp()
    resource_manager._save()
