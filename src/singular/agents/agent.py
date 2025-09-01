from __future__ import annotations

"""Core agent implementation handling motivations and goals."""

from dataclasses import dataclass, field
from random import choice, random
from typing import Dict, Optional

from singular.morals.moral_rules import score_action

from singular.models.agents.motivation import Motivation


@dataclass
class Agent:
    """Simple agent driven by motivations."""

    motivations: Motivation = field(default_factory=Motivation)
    decision_noise: float = 0.0
    moral_tolerance: float = 0.0

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

    def choose_action(
        self, actions: Dict[str, float], context: Optional[Dict] = None
    ) -> Optional[str]:
        """Select an action, considering moral constraints.

        ``actions`` maps action identifiers to a numeric value representing its
        desirability. Actions with a moral score lower than ``-moral_tolerance``
        are discarded. The remaining action with the highest value is normally
        chosen. With probability ``decision_noise`` a random non-optimal action
        is returned instead. If no permissible actions are available, ``None``
        is returned.
        """

        if not actions:
            return None

        context = context or {}
        allowed_actions = {
            act: val
            for act, val in actions.items()
            if score_action(act, context) >= -self.moral_tolerance
        }

        if not allowed_actions:
            return None

        best_action = max(allowed_actions, key=allowed_actions.get)
        # Explore a non-optimal action with probability ``decision_noise``
        if len(allowed_actions) > 1 and random() < self.decision_noise:
            alternatives = [act for act in allowed_actions if act != best_action]
            if alternatives:
                return choice(alternatives)

        return best_action
