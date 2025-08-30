from singular.psyche import Psyche, Mood
from singular.motivation import Objective

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
