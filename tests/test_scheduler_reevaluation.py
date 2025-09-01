import time

from singular.agents import Agent
from singular.schedulers import start


def test_scheduler_triggers_goal_reevaluation():
    agent = Agent()
    calls = {"count": 0}

    def spy() -> None:
        calls["count"] += 1

    # Replace choose_goal with spy to count invocations
    agent.choose_goal = spy  # type: ignore[assignment]

    stop_event = start(0.01, agent)
    time.sleep(0.05)
    stop_event.set()

    assert calls["count"] > 0

