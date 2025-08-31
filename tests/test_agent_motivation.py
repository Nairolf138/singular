from singular.models.agents import Motivation
from singular.agents import Agent


def test_update_and_choose_goal():
    agent = Agent()
    agent.update_motivations({"hunger": 1.0, "thirst": 0.5})
    agent.update_motivations({"thirst": 1.0})  # hunger=1.0, thirst=1.5
    assert agent.motivations.needs["thirst"] == 1.5
    assert agent.choose_goal() == "thirst"


def test_motivation_storage():
    motivation = Motivation({"rest": 0.2})
    assert motivation.needs["rest"] == 0.2
