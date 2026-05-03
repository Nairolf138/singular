from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from singular.memory import _atomic_write_text


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


@dataclass
class HierarchicalObjectivesState:
    immediate: dict[str, float] = field(default_factory=dict)
    meta: dict[str, float] = field(
        default_factory=lambda: {
            "future_learning_capacity": 0.5,
            "skills_diversity": 0.5,
            "technical_debt_control": 0.5,
        }
    )
    meta_failure_streak: int = 0


class HierarchicalObjectivesManager:
    """Persist and revise immediate/meta goals under perturbations and interruptions."""

    def __init__(self, *, path: Path) -> None:
        self.path = path
        self.state = self._load()

    def _load(self) -> HierarchicalObjectivesState:
        if not self.path.exists():
            return HierarchicalObjectivesState()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return HierarchicalObjectivesState()
        if not isinstance(payload, dict):
            return HierarchicalObjectivesState()
        immediate = payload.get("immediate", {})
        meta = payload.get("meta", {})
        return HierarchicalObjectivesState(
            immediate=dict(immediate) if isinstance(immediate, dict) else {},
            meta={**HierarchicalObjectivesState().meta, **(meta if isinstance(meta, dict) else {})},
            meta_failure_streak=int(payload.get("meta_failure_streak", 0) or 0),
        )

    def _save(self) -> None:
        _atomic_write_text(
            self.path,
            json.dumps(
                {
                    "immediate": self.state.immediate,
                    "meta": self.state.meta,
                    "meta_failure_streak": self.state.meta_failure_streak,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )

    def revise(self, *, perturbation: dict[str, Any] | None = None) -> HierarchicalObjectivesState:
        perturbation = perturbation or {}
        interruption_pressure = _clamp(float(perturbation.get("interruption_pressure", 0.0) or 0.0))
        for key, value in list(self.state.immediate.items()):
            self.state.immediate[key] = max(0.0, float(value) * (1.0 - (0.15 * interruption_pressure)))
        for key, value in list(self.state.meta.items()):
            decay = 0.03 if interruption_pressure < 0.35 else 0.01
            self.state.meta[key] = _clamp(float(value) * (1.0 - decay))
        self._save()
        return self.state

    def register_meta_outcome(self, *, success: bool) -> int:
        self.state.meta_failure_streak = 0 if success else self.state.meta_failure_streak + 1
        self._save()
        return self.state.meta_failure_streak

    def graded_vital_penalty(self) -> float:
        streak = max(0, int(self.state.meta_failure_streak))
        if streak < 2:
            return 0.0
        if streak < 4:
            return 1.5
        if streak < 7:
            return 3.0
        return 5.0
