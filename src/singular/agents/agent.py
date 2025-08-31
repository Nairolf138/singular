from __future__ import annotations

"""Core agent implementation handling motivations and goals."""

from dataclasses import dataclass, field
from typing import Dict, Optional

from singular.models.agents.motivation import Motivation


@dataclass
class Agent:
    """Simple agent driven by motivations."""

    motivations: Motivation = field(default_factory=Motivation)

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
