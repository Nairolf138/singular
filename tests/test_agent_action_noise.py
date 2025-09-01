from singular.agents import Agent


def test_choose_action_optimal_without_noise():
    agent = Agent()
    actions = {"a": 0.1, "b": 0.5}
    assert agent.choose_action(actions) == "b"


def test_choose_action_with_noise_selects_non_optimal():
    agent = Agent(decision_noise=1.0)
    actions = {"a": 0.1, "b": 0.5}
    # With decision_noise=1.0 the agent should always explore a non-optimal action
    assert agent.choose_action(actions) == "a"

