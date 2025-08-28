from singular.psyche import Psyche
from singular.motivation import Objective

def test_curiosity_increases():
    psyche = Psyche()
    base = psyche.curiosity
    psyche.feel("curious")
    assert psyche.curiosity > base

def test_objective_weights_adapt():
    psyche = Psyche(objectives={"goal": Objective("goal", weight=0.5)})
    base = psyche.objectives["goal"].weight
    psyche.feel("pleasure")
    increased = psyche.objectives["goal"].weight
    assert increased > base
    psyche.feel("pain")
    decreased = psyche.objectives["goal"].weight
    assert decreased < increased
