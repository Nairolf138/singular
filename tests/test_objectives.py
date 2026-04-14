from singular.psyche import Psyche, Mood
from singular.motivation import GoalPolicy, Objective
from singular.goals.intrinsic import IntrinsicGoals


def test_curiosity_increases():
    psyche = Psyche()
    base = psyche.curiosity
    psyche.feel(Mood.CURIOUS)
    assert psyche.curiosity > base


def test_objective_weights_adapt():
    psyche = Psyche(objectives={"goal": Objective("goal", weight=0.5)})
    base = psyche.objectives["goal"].weight
    psyche.feel(Mood.PLEASURE)
    increased = psyche.objectives["goal"].weight
    assert increased > base
    psyche.feel(Mood.PAIN)
    decreased = psyche.objectives["goal"].weight
    assert decreased < increased


def test_goal_policy_arbitration_bounds() -> None:
    policy = GoalPolicy(besoin=1.0, priorite=0.8, urgence=0.6, alignement_valeurs=0.9)
    score = policy.arbitration_score()
    assert 0.0 <= score <= 1.0


def test_intrinsic_goals_boost_robustesse_when_tech_debt_rises(tmp_path) -> None:
    goals = IntrinsicGoals(path=tmp_path / "goals.json")
    psyche = Psyche()

    without_debt_rise = goals.update_tick(
        tick=1,
        psyche=psyche,
        health_score=80.0,
        resources={"energy": 80.0, "food": 80.0, "warmth": 80.0},
        perception_signals={
            "tech_debt_previous_markers": 3,
            "artifact_events": [
                {"type": "artifact.tech_debt.simple", "data": {"markers": 3}},
            ],
        },
    )
    with_debt_rise = goals.update_tick(
        tick=2,
        psyche=psyche,
        health_score=80.0,
        resources={"energy": 80.0, "food": 80.0, "warmth": 80.0},
        perception_signals={
            "tech_debt_previous_markers": 3,
            "artifact_events": [
                {"type": "artifact.tech_debt.simple", "data": {"markers": 9}},
            ],
        },
    )

    assert with_debt_rise.robustesse > without_debt_rise.robustesse


def test_intrinsic_goals_adjust_coherence_and_efficacite_from_user_friction(tmp_path) -> None:
    goals = IntrinsicGoals(path=tmp_path / "goals.json")
    psyche = Psyche()

    low_friction = goals.update_tick(
        tick=1,
        psyche=psyche,
        health_score=75.0,
        resources={"energy": 75.0, "food": 75.0, "warmth": 75.0},
        perception_signals={"episode_memory": {"user_friction": 0.1}},
    )
    high_friction = goals.update_tick(
        tick=2,
        psyche=psyche,
        health_score=75.0,
        resources={"energy": 75.0, "food": 75.0, "warmth": 75.0},
        perception_signals={"episode_memory": {"user_friction": 0.9}},
    )

    assert high_friction.coherence > low_friction.coherence
    assert high_friction.efficacite > low_friction.efficacite


def test_intrinsic_goals_uses_skill_reputation_telemetry(tmp_path) -> None:
    goals = IntrinsicGoals(path=tmp_path / "goals.json")
    psyche = Psyche()

    baseline = goals.update_tick(
        tick=1,
        psyche=psyche,
        health_score=80.0,
        resources={"energy": 80.0, "food": 80.0, "warmth": 80.0},
        perception_signals={},
    )
    with_telemetry = goals.update_tick(
        tick=2,
        psyche=psyche,
        health_score=80.0,
        resources={"energy": 80.0, "food": 80.0, "warmth": 80.0},
        perception_signals={
            "skill_reputation": {
                "skill_a": {"mean_cost": 180.0, "mean_quality": 0.25, "recent_failures": 4},
            }
        },
    )

    assert with_telemetry.efficacite > baseline.efficacite
    assert with_telemetry.coherence > baseline.coherence


def test_intrinsic_goals_account_for_host_environment_pressure(tmp_path) -> None:
    goals = IntrinsicGoals(path=tmp_path / "goals.json")
    psyche = Psyche()

    low_pressure = goals.update_tick(
        tick=1,
        psyche=psyche,
        health_score=80.0,
        resources={"energy": 80.0, "food": 80.0, "warmth": 80.0},
        perception_signals={
            "host_metrics_aggregates": {
                "rolling_means": {
                    "cpu_percent": {"20": 18.0},
                    "ram_used_percent": {"20": 22.0},
                    "host_temperature_c": {"20": 35.0},
                },
                "variance": {"cpu_percent": 5.0, "ram_used_percent": 7.0},
            }
        },
    )
    high_pressure = goals.update_tick(
        tick=2,
        psyche=psyche,
        health_score=80.0,
        resources={"energy": 80.0, "food": 80.0, "warmth": 80.0},
        perception_signals={
            "host_metrics_aggregates": {
                "rolling_means": {
                    "cpu_percent": {"20": 90.0},
                    "ram_used_percent": {"20": 91.0},
                    "host_temperature_c": {"20": 84.0},
                },
                "variance": {"cpu_percent": 110.0, "ram_used_percent": 95.0},
            }
        },
    )

    assert high_pressure.robustesse > low_pressure.robustesse
    assert high_pressure.efficacite < low_pressure.efficacite


def test_intrinsic_goals_strategy_turns_cautious_on_repeated_negative_feedback(tmp_path) -> None:
    goals = IntrinsicGoals(path=tmp_path / "goals.json")
    strategy = goals.derive_execution_strategy(
        {
            "episode_memory": {
                "structured_feedback": {
                    "frustration": 0.8,
                    "satisfaction": 0.1,
                    "urgency": 0.4,
                    "theme": "support",
                },
                "negative_feedback_streak": 3,
            }
        }
    )
    assert strategy["mode"] == "cautious"


def test_intrinsic_goals_adjust_routine_priorities_from_urgency(tmp_path) -> None:
    goals = IntrinsicGoals(path=tmp_path / "goals.json")
    adjusted = goals.adjust_routine_priorities(
        [
            {"id": "deep_research", "prompt": "explore roadmap", "priority": 70},
            {"id": "user_support", "prompt": "help user quickly", "priority": 50},
        ],
        perception_signals={
            "episode_memory": {
                "structured_feedback": {"frustration": 0.2, "satisfaction": 0.2, "urgency": 0.8, "theme": "support"}
            }
        },
    )
    assert adjusted[0]["id"] == "user_support"
