from __future__ import annotations

import random

from singular.life.ecosystem import ARCHETYPES, compute_population_metrics, draw_global_event


def test_archetypes_are_available() -> None:
    assert set(ARCHETYPES) == {"explorer", "stabilizer", "parasite", "guardian"}


def test_global_event_draw_is_supported() -> None:
    event = draw_global_event(random.Random(7))
    assert event.event_type in {"resource_crisis", "governance_shift", "simulated_catastrophe"}
    assert 0.2 <= event.intensity <= 0.9


def test_population_reorganization_metrics() -> None:
    before = {"a": (1.0, 1.0), "b": (1.0, 0.5)}
    after = {"a": (0.8, 0.9), "b": (0.4, 0.2)}
    metrics = compute_population_metrics(before, after, ticks_elapsed=3)
    assert metrics["resilience"] > 0
    assert 0 <= metrics["diversity"] <= 1
    assert metrics["recovery_time"] == 3.0
