"""Incident taxonomy and adaptive immune response primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from math import exp


@dataclass(frozen=True)
class DangerousIncidentTaxonomy:
    """Taxonomy for dangerous incident classes."""

    toxic_mutational_patterns: tuple[str, ...] = (
        "semantic_drift",
        "constraint_bypass",
        "unsafe_capability_escalation",
    )
    critical_regressions: tuple[str, ...] = (
        "safety_guard_removed",
        "core_metric_collapse",
        "test_suite_breakage",
    )
    internal_quasi_sabotage: tuple[str, ...] = (
        "self_disable_protection",
        "policy_circumvention_attempt",
        "latent_backdoor_introduction",
    )

    def classify(self, pattern: str) -> str:
        if pattern in self.toxic_mutational_patterns:
            return "toxic_mutation_pattern"
        if pattern in self.critical_regressions:
            return "critical_regression"
        if pattern in self.internal_quasi_sabotage:
            return "internal_quasi_sabotage"
        return "unknown"


@dataclass(frozen=True)
class IncidentRecord:
    """One observed dangerous incident."""

    pattern: str
    happened_at: datetime
    recurred: bool = False


@dataclass(frozen=True)
class ImmuneResponsePlan:
    """Auto-generated immune response after an incident."""

    targeted_tests: tuple[str, ...]
    hardened_rules: tuple[str, ...]
    temporary_blacklist: tuple[str, ...]
    blacklist_ttl_seconds: float


@dataclass
class ImmuneMemoryEntry:
    pattern: str
    weight: float = 1.0
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class ImmuneMetrics:
    recurrence_rate: float
    defense_cost: float
    learning_speed_impact: float


class AdaptiveImmunityEngine:
    """Maintain incident memory with decay and response automation."""

    def __init__(self, *, half_life_seconds: float = 3600.0) -> None:
        self.taxonomy = DangerousIncidentTaxonomy()
        self.half_life_seconds = max(float(half_life_seconds), 1.0)
        self._memory: dict[str, ImmuneMemoryEntry] = {}
        self._blacklist_until: dict[str, datetime] = {}

    def trigger_response(self, incident: IncidentRecord) -> ImmuneResponsePlan:
        category = self.taxonomy.classify(incident.pattern)
        self._reinforce(incident.pattern, when=incident.happened_at)

        tests = (f"test_guard_{incident.pattern}", f"test_non_regression_{category}")
        rules = (
            f"deny_pattern:{incident.pattern}",
            f"elevate_review:{category}",
        )

        ttl = 600.0 if incident.recurred else 300.0
        self._blacklist_until[incident.pattern] = incident.happened_at + timedelta(seconds=ttl)

        return ImmuneResponsePlan(
            targeted_tests=tests,
            hardened_rules=rules,
            temporary_blacklist=(incident.pattern,),
            blacklist_ttl_seconds=ttl,
        )

    def decay_memory(self, now: datetime | None = None) -> None:
        current = now or datetime.now(timezone.utc)
        for pattern, entry in list(self._memory.items()):
            elapsed = max((current - entry.updated_at).total_seconds(), 0.0)
            decayed_weight = entry.weight * exp(-elapsed / self.half_life_seconds)
            if decayed_weight < 0.05:
                del self._memory[pattern]
                continue
            self._memory[pattern] = ImmuneMemoryEntry(
                pattern=pattern,
                weight=decayed_weight,
                updated_at=current,
            )

    def is_temporarily_blacklisted(self, pattern: str, now: datetime | None = None) -> bool:
        current = now or datetime.now(timezone.utc)
        expires_at = self._blacklist_until.get(pattern)
        if expires_at is None:
            return False
        if current >= expires_at:
            del self._blacklist_until[pattern]
            return False
        return True

    def evaluate_effectiveness(
        self,
        *,
        incidents: list[IncidentRecord],
        defense_actions_count: int,
        baseline_learning_velocity: float,
        current_learning_velocity: float,
    ) -> ImmuneMetrics:
        if not incidents:
            return ImmuneMetrics(0.0, float(defense_actions_count), 0.0)

        recurrences = sum(1 for item in incidents if item.recurred)
        recurrence_rate = recurrences / len(incidents)
        defense_cost = float(defense_actions_count) / len(incidents)
        if baseline_learning_velocity <= 0:
            learning_impact = 0.0
        else:
            learning_impact = (baseline_learning_velocity - current_learning_velocity) / baseline_learning_velocity

        return ImmuneMetrics(
            recurrence_rate=max(0.0, recurrence_rate),
            defense_cost=max(0.0, defense_cost),
            learning_speed_impact=max(-1.0, min(1.0, learning_impact)),
        )

    def memory_snapshot(self) -> dict[str, float]:
        return {pattern: entry.weight for pattern, entry in self._memory.items()}

    def _reinforce(self, pattern: str, *, when: datetime) -> None:
        existing = self._memory.get(pattern)
        if existing is None:
            self._memory[pattern] = ImmuneMemoryEntry(pattern=pattern, weight=1.0, updated_at=when)
            return
        self._memory[pattern] = ImmuneMemoryEntry(
            pattern=pattern,
            weight=existing.weight + 1.0,
            updated_at=when,
        )
