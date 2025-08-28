from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Objective:
    """Simple structure describing an objective with a weight and reward."""

    name: str
    weight: float = 1.0
    reward: float = 0.0

    def apply_delta(self, delta: float) -> None:
        """Adjust weight by ``delta`` and accumulate reward."""
        self.weight += delta
        self.reward += delta
