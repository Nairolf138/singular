"""Goal-aware intrinsic motivation with an explicit exploration budget."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


def _unit(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


@dataclass(frozen=True)
class CuriosityWeights:
    novelty: float = 1.0
    prediction_error: float = 1.0
    information_gain: float = 1.0
    cost: float = 1.0
    risk: float = 2.0
    relevance: float = 1.0


class CuriosityEngine:
    """Ranks experiments and stops spending after unproductive attempts."""

    def __init__(
        self,
        weights: CuriosityWeights | None = None,
        *,
        budget: float = 3.0,
        min_score: float = 0.05,
        max_unproductive: int = 2,
    ) -> None:
        self.weights = weights or CuriosityWeights()
        self.remaining_budget = max(0.0, float(budget))
        self.min_score = float(min_score)
        self.max_unproductive = max(1, int(max_unproductive))
        self.unproductive_attempts = 0

    def score(
        self,
        *,
        novelty: float,
        prediction_error: float,
        expected_information_gain: float,
        cost: float,
        risk: float,
        goal_relevance: float | Mapping[str, float],
        goal_weights: Mapping[str, float] | None = None,
    ) -> float:
        """Return the weighted utility; inputs are clipped to comparable units."""

        if isinstance(goal_relevance, Mapping):
            weights = goal_weights or {}
            denominator = sum(
                max(0.0, float(weights.get(k, 1.0))) for k in goal_relevance
            )
            relevance = (
                sum(
                    _unit(v) * max(0.0, float(weights.get(k, 1.0)))
                    for k, v in goal_relevance.items()
                )
                / denominator
                if denominator
                else 0.0
            )
        else:
            relevance = _unit(goal_relevance)
        w = self.weights
        return (
            w.novelty * _unit(novelty)
            + w.prediction_error * _unit(prediction_error)
            + w.information_gain * _unit(expected_information_gain)
            + w.relevance * relevance
            - w.cost * _unit(cost)
            - w.risk * _unit(risk)
        )

    def authorize(self, score: float, *, cost: float = 1.0) -> bool:
        charge = max(0.0, float(cost))
        return (
            score >= self.min_score
            and charge <= self.remaining_budget
            and self.unproductive_attempts < self.max_unproductive
        )

    def record_result(self, *, information_gain: float, cost: float = 1.0) -> None:
        self.remaining_budget = max(0.0, self.remaining_budget - max(0.0, float(cost)))
        if information_gain <= 0.0:
            self.unproductive_attempts += 1
        else:
            self.unproductive_attempts = 0
