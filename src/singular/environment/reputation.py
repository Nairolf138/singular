from __future__ import annotations

"""Reputation tracking based on moral evaluation of actions."""

from typing import Dict, Any

from singular.morals.moral_rules import score_action


class ReputationSystem:
    """Maintain and update reputations for agents."""

    def __init__(self) -> None:
        self.reputations: Dict[str, float] = {}

    def update(self, agent_id: str, action: str, context: Dict[str, Any] | None = None) -> float:
        """Update the reputation of ``agent_id`` after performing ``action``.

        The adjustment is based on the moral score of ``action``. Returns the
        new reputation value.
        """

        context = context or {}
        score = score_action(action, context)
        self.reputations[agent_id] = self.reputations.get(agent_id, 0.0) + score
        return self.reputations[agent_id]

    def get(self, agent_id: str) -> float:
        """Return the reputation for ``agent_id`` (defaults to 0)."""

        return self.reputations.get(agent_id, 0.0)
