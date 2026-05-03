from __future__ import annotations

from datetime import datetime, timedelta, timezone

from security.immune_response import AdaptiveImmunityEngine, IncidentRecord


def test_trigger_response_builds_targeted_actions_and_blacklist() -> None:
    engine = AdaptiveImmunityEngine()
    now = datetime(2026, 5, 3, tzinfo=timezone.utc)

    plan = engine.trigger_response(
        IncidentRecord(pattern="semantic_drift", happened_at=now, recurred=True)
    )

    assert "test_guard_semantic_drift" in plan.targeted_tests
    assert "deny_pattern:semantic_drift" in plan.hardened_rules
    assert plan.blacklist_ttl_seconds == 600.0
    assert engine.is_temporarily_blacklisted("semantic_drift", now + timedelta(seconds=1))


def test_memory_decay_forgets_weak_entries() -> None:
    engine = AdaptiveImmunityEngine(half_life_seconds=10.0)
    start = datetime(2026, 5, 3, tzinfo=timezone.utc)
    engine.trigger_response(IncidentRecord(pattern="constraint_bypass", happened_at=start))

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
