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
