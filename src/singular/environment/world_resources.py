"""Global world-level resource pool with cooperation and competition rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass(frozen=True)
class CompetitorIntent:
    """Simple bidding intent used to arbitrate contention."""

    life_id: str
    priority: int = 0
    bid: float = 0.0


@dataclass
class ActionResolution:
    """Outcome of a resource request for one life action."""

    granted: bool
    consumed: dict[str, float]
    cooperation_partners: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    contention: bool = False
    relation_bonus: float = 0.0
    rivalry_penalty: float = 0.0
    arbitration_winner: str | None = None


@dataclass
class WorldResourcePool:
    """Finite shared resources consumed by every life action."""

    cpu_budget: float = 100.0
    mutation_slots: float = 8.0
    attention_score: float = 50.0
    contention_log: list[dict[str, Any]] = field(default_factory=list)

    def replenish(
        self,
        *,
        cpu_budget: float | None = None,
        mutation_slots: float | None = None,
        attention_score: float | None = None,
    ) -> None:
        """Reset available resources for a new world cycle."""

        if cpu_budget is not None:
            self.cpu_budget = max(float(cpu_budget), 0.0)
        if mutation_slots is not None:
            self.mutation_slots = max(float(mutation_slots), 0.0)
        if attention_score is not None:
            self.attention_score = max(float(attention_score), 0.0)

    def consume_for_action(
        self,
        *,
        life_id: str,
        cpu_cost: float,
        mutation_cost: float,
        attention_cost: float,
        cooperation_partners: Iterable[str] = (),
        priority: int = 0,
        bid: float = 0.0,
        competitor_intents: Iterable[CompetitorIntent] = (),
    ) -> ActionResolution:
        """Consume resources for one action and persist contention/conflict events."""

        cooperation = [name for name in cooperation_partners if name and name != life_id]
        effective_cpu = max(float(cpu_cost), 0.0)
        effective_mut = max(float(mutation_cost), 0.0)
        effective_attention = max(float(attention_cost), 0.0)
        if cooperation:
            # Cooperation reduces total demand, then costs are shared.
            effective_cpu *= 0.85
            effective_mut *= 0.85
            effective_attention *= 0.85

        actor_score = (max(int(priority), 0) * 10.0) + max(float(bid), 0.0)
        contenders = [CompetitorIntent(life_id=life_id, priority=priority, bid=bid)]
        contenders.extend(competitor_intents)
        winner = max(contenders, key=lambda item: (item.priority * 10.0) + item.bid)
        granted = winner.life_id == life_id
        scarcity = (
            self.cpu_budget < effective_cpu
            or self.mutation_slots < effective_mut
            or self.attention_score < effective_attention
        )
        contention = scarcity or len(contenders) > 1
        conflicts = [intent.life_id for intent in contenders if intent.life_id != winner.life_id]
        if scarcity and not granted:
            consumed = {"cpu_budget": 0.0, "mutation_slots": 0.0, "attention_score": 0.0}
            rivalry_penalty = 0.2 + (max(winner.bid - actor_score, 0.0) * 0.01)
            relation_bonus = 0.0
        else:
            granted = True
            self.cpu_budget = max(self.cpu_budget - effective_cpu, 0.0)
            self.mutation_slots = max(self.mutation_slots - effective_mut, 0.0)
            self.attention_score = max(self.attention_score - effective_attention, 0.0)
            consumed = {
                "cpu_budget": effective_cpu,
                "mutation_slots": effective_mut,
                "attention_score": effective_attention,
            }
            relation_bonus = 0.1 * len(cooperation)
            rivalry_penalty = 0.0 if cooperation else (0.05 * len(conflicts) if contention else 0.0)

        event = {
            "life_id": life_id,
            "cooperation_partners": cooperation,
            "requested": {
                "cpu_budget": cpu_cost,
                "mutation_slots": mutation_cost,
                "attention_score": attention_cost,
            },
            "consumed": consumed,
            "contention": contention,
            "conflicts": conflicts if contention else [],
            "winner": winner.life_id if contention else life_id,
            "remaining": {
                "cpu_budget": self.cpu_budget,
                "mutation_slots": self.mutation_slots,
                "attention_score": self.attention_score,
            },
            "granted": granted,
        }
        self.contention_log.append(event)
        self.contention_log = self.contention_log[-300:]
        return ActionResolution(
            granted=granted,
            consumed=consumed,
            cooperation_partners=cooperation,
            conflicts=event["conflicts"],
            contention=contention,
            relation_bonus=relation_bonus,
            rivalry_penalty=rivalry_penalty,
            arbitration_winner=winner.life_id if contention else None,
        )
