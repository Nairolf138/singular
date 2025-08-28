from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from singular.psyche import Psyche


@dataclass
class DeathMonitor:
    """Track mortality conditions for an organism."""

    max_failures: int = 5
    max_age: int = 1000
    min_trait: float = 0.05
    failures: int = 0

    def check(
        self, iteration: int, psyche: Psyche, success: bool
    ) -> Tuple[bool, str | None]:
        """Update state and return ``(dead, reason)`` for current iteration."""
        if not success:
            self.failures += 1
        else:
            self.failures = 0

        if self.failures >= self.max_failures:
            return True, "too many failures"
        if iteration >= self.max_age:
            return True, "old age"
        traits_low = [
            getattr(psyche, attr, 1.0) <= self.min_trait
            for attr in ("curiosity", "patience", "playfulness")
        ]
        if all(traits_low):
            return True, "traits exhausted"
        return False, None
