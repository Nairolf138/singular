from singular.psyche import Psyche, Mood
from singular.motivation import GoalPolicy, Objective


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
