from __future__ import annotations

"""Core agent implementation handling motivations and goals."""

from dataclasses import dataclass, field
from random import choice, random
from typing import Dict, Optional

from singular.models.agents.motivation import Motivation


@dataclass
class Agent:
    """Simple agent driven by motivations."""

    motivations: Motivation = field(default_factory=Motivation)
    decision_noise: float = 0.0

    def update_motivations(self, context: Dict[str, float]) -> None:
        """Adjust motivation priorities based on ``context``.

        ``context`` is a mapping of need names to delta values. Each delta is
        added to the current motivation for that need. Missing needs are
        initialised to zero before applying the delta.
        """

        for need, delta in context.items():
            self.motivations.needs[need] = (
                self.motivations.needs.get(need, 0.0) + delta
            )

    def choose_goal(self) -> Optional[str]:
        """Return the need with the highest motivation.

        If no needs are present, ``None`` is returned.
        """

        if not self.motivations.needs:
            return None
        return max(self.motivations.needs, key=self.motivations.needs.get)

    def choose_action(self, actions: Dict[str, float]) -> Optional[str]:
        """Select an action, occasionally exploring suboptimal options.

        ``actions`` maps action identifiers to a numeric value representing its
        desirability. The action with the highest value is normally chosen. With
        probability ``decision_noise`` a random non-optimal action is returned
        instead. If ``actions`` is empty, ``None`` is returned.
        """

        if not actions:
            return None

        best_action = max(actions, key=actions.get)
        # Explore a non-optimal action with probability ``decision_noise``
        if len(actions) > 1 and random() < self.decision_noise:
            alternatives = [act for act in actions if act != best_action]
            if alternatives:
                return choice(alternatives)

        return best_action
