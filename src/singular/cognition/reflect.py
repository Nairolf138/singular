"""Action reflection utilities.

The reflection pass compares multiple candidate hypotheses and picks the
highest-scoring action according to:
1) long-term objective contribution,
2) sandbox risk,
3) resource cost.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ActionHypothesis:
    """One candidate action scored by reflection heuristics."""

    action: str
    long_term: float
    sandbox_risk: float
    resource_cost: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReflectionDecision:
    """Structured decision outcome for auditing."""

    action: str | None
    decision_reason: str
    alternative_scores: dict[str, float]
    ranked_actions: list[str]


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _hypothesis_score(
    hypothesis: ActionHypothesis,
    *,
    long_term_weight: float,
    sandbox_weight: float,
    resource_weight: float,
) -> float:
    long_term = _clamp(hypothesis.long_term)
    sandbox_risk = _clamp(hypothesis.sandbox_risk)
    resource_cost = _clamp(hypothesis.resource_cost)
    return (
        (long_term_weight * long_term)
        - (sandbox_weight * sandbox_risk)
        - (resource_weight * resource_cost)
    )


def reflect_action(
    hypotheses: list[ActionHypothesis],
    *,
    long_term_weight: float = 0.6,
    sandbox_weight: float = 0.25,
    resource_weight: float = 0.15,
) -> ReflectionDecision:
    """Select the best action from candidate hypotheses."""

    if not hypotheses:
        return ReflectionDecision(
            action=None,
            decision_reason="no hypothesis available",
            alternative_scores={},
            ranked_actions=[],
        )

    scores = {
        hyp.action: _hypothesis_score(
            hyp,
            long_term_weight=long_term_weight,
            sandbox_weight=sandbox_weight,
            resource_weight=resource_weight,
        )
        for hyp in hypotheses
    }
    ranked = sorted(scores, key=lambda action: scores[action], reverse=True)
    selected = ranked[0]
    reason = (
        "selected highest weighted score "
        f"(long_term={long_term_weight:.2f}, sandbox={sandbox_weight:.2f}, "
        f"resources={resource_weight:.2f})"
    )
    return ReflectionDecision(
        action=selected,
        decision_reason=reason,
        alternative_scores=scores,
        ranked_actions=ranked,
    )
