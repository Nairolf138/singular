"""Periodic reevaluation of an agent's goals."""

from __future__ import annotations

import threading
import time

from singular.agents import Agent


def reevaluate_goals(agent: Agent) -> None:
    """Trigger the agent to reconsider its current goal."""

    agent.choose_goal()


def start(interval: float, agent: Agent) -> threading.Event:
    """Start a background scheduler calling ``reevaluate_goals``.

    The scheduler reevaluates ``agent``'s goals every ``interval`` seconds.
    A :class:`threading.Event` is returned which can be set to stop the
    scheduler.
    """

    stop_event = threading.Event()

    def loop() -> None:
        while not stop_event.is_set():
            reevaluate_goals(agent)
            time.sleep(interval)

    threading.Thread(target=loop, daemon=True).start()
    return stop_event


__all__ = ["reevaluate_goals", "start"]

