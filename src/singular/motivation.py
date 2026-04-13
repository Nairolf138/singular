from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Objective:
    """Structure describing an objective and its policy/arbitration metadata."""

    name: str
    weight: float = 1.0
    reward: float = 0.0
    parent: str | None = None
    horizon_ticks: int | None = None
    policy: GoalPolicy = field(default_factory=lambda: GoalPolicy())

    def apply_delta(self, delta: float) -> None:
        """Adjust weight by ``delta`` and accumulate reward."""
        self.weight += delta
        self.reward += delta

    def arbitration_score(self) -> float:
        """Return a normalized policy score in ``[0, 1]``."""
        return self.policy.arbitration_score()


@dataclass(frozen=True)
class GoalPolicy:
    """Policy describing how a goal should be prioritized.

    Parameters are expected in the ``[0, 1]`` range:
    - ``besoin``: intrinsic need pressure.
    - ``priorite``: strategic priority.
    - ``urgence``: temporal urgency.
    - ``alignement_valeurs``: value alignment consistency.
    """

    besoin: float = 0.5
    priorite: float = 0.5
    urgence: float = 0.5
    alignement_valeurs: float = 0.5

    def arbitration_score(self) -> float:
        """Aggregate policy dimensions into one arbitration scalar."""
        return (
            0.35 * _clamp(self.besoin)
            + 0.25 * _clamp(self.priorite)
            + 0.25 * _clamp(self.urgence)
            + 0.15 * _clamp(self.alignement_valeurs)
        )


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))
