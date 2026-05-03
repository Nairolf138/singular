from __future__ import annotations

from dataclasses import dataclass
from collections import deque
from typing import Tuple

from singular.psyche import Psyche


@dataclass
class DeathMonitor:
    """Track mortality conditions for an organism."""

    max_failures: int = 5
    max_age: int = 1000
    min_trait: float = 0.05
    failures: int = 0
    homeostasis_window: int = 12
    homeostasis_viability_min_ratio: float = 0.35
    homeostasis_history: deque[bool] | None = None

    def __post_init__(self) -> None:
        if self.homeostasis_history is None:
            self.homeostasis_history = deque(maxlen=max(1, self.homeostasis_window))

    def check(
        self,
        iteration: int,
        psyche: Psyche,
        action_succeeded: bool,
        resources: float | None = None,
        homeostasis_viable: bool = True,
    ) -> Tuple[bool, str | None]:
        """Update state and return ``(dead, reason)`` for current iteration."""
        if not action_succeeded:
            self.failures += 1
        else:
            self.failures = 0

        assert self.homeostasis_history is not None
        self.homeostasis_history.append(bool(homeostasis_viable))
        if len(self.homeostasis_history) == self.homeostasis_history.maxlen:
            viable_ratio = sum(1 for v in self.homeostasis_history if v) / len(self.homeostasis_history)
            if viable_ratio < self.homeostasis_viability_min_ratio:
                return True, "homeostasis collapse"

        if self.failures >= self.max_failures:
            return True, "too many failures"
        if iteration >= self.max_age:
            return True, "old age"
        if getattr(psyche, "energy", 1.0) <= 0:
            return True, "energy depleted"
        if resources is not None and resources <= 0:
            return True, "resources exhausted"
        traits_low = [
            getattr(psyche, attr, 1.0) <= self.min_trait
            for attr in ("curiosity", "patience", "playfulness")
        ]
        if all(traits_low):
            return True, "traits exhausted"
        return False, None
