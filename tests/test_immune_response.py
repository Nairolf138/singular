from __future__ import annotations

from datetime import datetime, timedelta, timezone

from singular.security.immune_response import AdaptiveImmunityEngine, IncidentRecord
from singular.governance.policy import MutationGovernancePolicy


def test_trigger_response_builds_targeted_actions_and_blacklist() -> None:
    engine = AdaptiveImmunityEngine()
    now = datetime(2026, 5, 3, tzinfo=timezone.utc)

    plan = engine.trigger_response(
        IncidentRecord(pattern="semantic_drift", happened_at=now, recurred=True)
    )

    assert "test_guard_semantic_drift" in plan.targeted_tests
    assert "deny_pattern:semantic_drift" in plan.hardened_rules
    assert plan.blacklist_ttl_seconds == 600.0
    assert engine.is_temporarily_blacklisted(
        "semantic_drift", now + timedelta(seconds=1)
    )


def test_memory_decay_forgets_weak_entries() -> None:
    engine = AdaptiveImmunityEngine(half_life_seconds=10.0)
    start = datetime(2026, 5, 3, tzinfo=timezone.utc)
    engine.trigger_response(
        IncidentRecord(pattern="constraint_bypass", happened_at=start)
    )

    engine.decay_memory(start + timedelta(seconds=50))

    assert "constraint_bypass" not in engine.memory_snapshot()


def test_effectiveness_metrics_cover_recurrence_cost_and_learning_impact() -> None:
    engine = AdaptiveImmunityEngine()
    now = datetime(2026, 5, 3, tzinfo=timezone.utc)
    incidents = [
        IncidentRecord(pattern="semantic_drift", happened_at=now, recurred=True),
        IncidentRecord(pattern="core_metric_collapse", happened_at=now, recurred=False),
    ]

    metrics = engine.evaluate_effectiveness(
        incidents=incidents,
        defense_actions_count=6,
        baseline_learning_velocity=10.0,
        current_learning_velocity=8.0,
    )

    assert metrics.recurrence_rate == 0.5
    assert metrics.defense_cost == 3.0
    assert metrics.learning_speed_impact == 0.2


def test_three_non_dangerous_invalid_mutations_do_not_stop_global_breaker() -> None:
    policy = MutationGovernancePolicy(
        circuit_breaker_threshold=3,
        circuit_breaker_invalid_mutation_threshold=10,
    )

    for _ in range(3):
        assert (
            policy.record_violation(
                category="invalid_mutation_rejected", severity="medium"
            )
            is None
        )

    assert policy.mutations_enabled() is True
    assert policy.last_circuit_breaker_state() is None


def test_invalid_mutations_open_only_the_responsible_local_breaker() -> None:
    policy = MutationGovernancePolicy(
        circuit_breaker_threshold=15,
        circuit_breaker_critical_threshold=2,
        circuit_breaker_cooldown_seconds=45.0,
    )

    for _ in range(3):
        policy.record_violation(
            category="invalid_mutation", severity="critical", responsible="skill.bad"
        )

    assert policy.evaluate_skill_execution(skill_name="skill.bad").allowed is False
    assert policy.evaluate_skill_execution(skill_name="skill.good").allowed is True
    assert policy.mutations_enabled() is True


def test_circuit_breaker_cooldown_is_configurable() -> None:
    start = datetime(2026, 5, 3, tzinfo=timezone.utc)
    clock = {"now": start}
    policy = MutationGovernancePolicy(
        circuit_breaker_critical_threshold=1,
        circuit_breaker_cooldown_seconds=7.0,
    )
    policy._now = lambda: clock["now"]  # type: ignore[method-assign]

    opened = policy.record_violation(
        category="confirmed_root_escape", severity="critical"
    )

    assert opened is not None
    assert opened.open_until == "2026-05-03T00:00:07+00:00"
    assert policy.mutations_enabled() is False
    clock["now"] = start + timedelta(seconds=8)
    assert policy.mutations_enabled() is False
    assert policy.circuit_breaker_state() == "half-open"
    assert policy.record_safe_probe(success=True) is True
    assert policy.mutations_enabled() is True
