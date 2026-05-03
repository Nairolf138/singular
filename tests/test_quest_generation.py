from singular.goals.quest_generation import generate_quests


def test_generate_quests_mixes_intrinsic_and_external_pressures() -> None:
    quests = generate_quests(
        psyche_traits={"resilience": 0.2, "optimism": 0.3, "curiosity": 0.8},
        outcomes_history={"recent_successes": 1, "recent_failures": 4},
        value_performance_tension={"score": 0.75},
        world_state={"delayed_crisis_pressure": 0.7, "opportunity_pressure": 0.65},
        resources={"energy": 20, "food": 25, "warmth": 30},
    )

    assert quests
    origins = {item.origin for item in quests}
    assert "intrinsic" in origins
    assert "external" in origins
    assert quests == sorted(quests, key=lambda item: item.priority, reverse=True)


def test_generate_quests_returns_empty_for_stable_state() -> None:
    quests = generate_quests(
        psyche_traits={"resilience": 0.8, "optimism": 0.9, "curiosity": 0.2},
        outcomes_history={"recent_successes": 5, "recent_failures": 0},
        value_performance_tension=0.1,
        world_state={"delayed_crisis_pressure": 0.1, "opportunity_pressure": 0.1},
        resources={"energy": 90, "food": 85, "warmth": 95},
    )

    assert quests == []


def test_generate_quests_adds_internal_probe_from_surprise_frustration() -> None:
    quests = generate_quests(
        psyche_traits={"resilience": 0.5, "optimism": 0.5, "curiosity": 0.5},
        outcomes_history={"recent_successes": 2, "recent_failures": 2},
        value_performance_tension=0.0,
        world_state={"delayed_crisis_pressure": 0.1, "opportunity_pressure": 0.1},
        resources={"energy": 70, "food": 70, "warmth": 70},
        surprise_signals={
            "surprise": 0.7,
            "frustration": 0.8,
            "curiosity": 0.9,
            "operator_family_failure_pressure": 0.8,
        },
    )

    assert any(item.name == "probe_operator_failure_cluster" for item in quests)
