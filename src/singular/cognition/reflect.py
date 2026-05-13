"""Action reflection utilities.

The reflection pass compares multiple candidate hypotheses and picks the
highest-scoring action according to:
1) long-term objective contribution,
2) sandbox risk,
3) resource cost.

In addition to the selected action, the module emits a structured decision
trace containing the assumptions considered, expected benefits, explicit risks,
confidence, and the next recommended action for downstream audit/logging.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from singular.events import EventBus, get_global_event_bus


@dataclass(frozen=True)
class ActionHypothesis:
    """One candidate action scored by reflection heuristics."""

    action: str
    long_term: float
    sandbox_risk: float
    resource_cost: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReflectionAssessment:
    """Structured assessment attached to one candidate action."""

    action: str
    score: float
    hypotheses: list[str]
    risks: list[str]
    benefits: list[str]
    confidence: float
    action_recommended: str


@dataclass(frozen=True)
class ReflectionDecision:
    """Structured decision outcome for auditing."""

    action: str | None
    decision_reason: str
    alternative_scores: list[tuple[int, str, float]]
    ranked_actions: list[str]
    hypotheses: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    benefits: list[str] = field(default_factory=list)
    confidence: float = 0.0
    action_recommended: str | None = None
    assessments: list[ReflectionAssessment] = field(default_factory=list)

    def to_event_payload(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation for event publication."""

        return {
            "action": self.action,
            "decision_reason": self.decision_reason,
            "alternative_scores": self.alternative_scores,
            "ranked_actions": self.ranked_actions,
            "hypotheses": self.hypotheses,
            "risks": self.risks,
            "benefits": self.benefits,
            "confidence": self.confidence,
            "action_recommended": self.action_recommended,
            "assessments": [assessment.__dict__ for assessment in self.assessments],
        }


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


def _metadata_list(metadata: Mapping[str, Any], key: str) -> list[str]:
    value = metadata.get(key)
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, list | tuple | set):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _assessment_for(
    hypothesis: ActionHypothesis,
    *,
    score: float,
    max_abs_score: float,
) -> ReflectionAssessment:
    long_term = _clamp(hypothesis.long_term)
    sandbox_risk = _clamp(hypothesis.sandbox_risk)
    resource_cost = _clamp(hypothesis.resource_cost)
    hypotheses = _metadata_list(hypothesis.metadata, "hypotheses") or [
        f"{hypothesis.action} can contribute {long_term:.2f} to long-term objectives",
    ]
    benefits = _metadata_list(hypothesis.metadata, "benefits") or [
        f"long_term_benefit={long_term:.2f}",
    ]
    risks = _metadata_list(hypothesis.metadata, "risks")
    if sandbox_risk > 0.0:
        risks.append(f"sandbox_risk={sandbox_risk:.2f}")
    if resource_cost > 0.0:
        risks.append(f"resource_cost={resource_cost:.2f}")
    if not risks:
        risks.append("no material risk identified")

    confidence = _clamp(0.5 + (score / (2.0 * max(max_abs_score, 1e-9))))
    recommendation = "execute" if score >= 0.0 else "defer_or_revise"
    return ReflectionAssessment(
        action=hypothesis.action,
        score=score,
        hypotheses=hypotheses,
        risks=risks,
        benefits=benefits,
        confidence=confidence,
        action_recommended=recommendation,
    )


def _publish_decision(
    decision: ReflectionDecision,
    *,
    bus: EventBus | None,
    event_context: Mapping[str, Any] | None,
) -> None:
    emitter = bus or get_global_event_bus()
    emitter.publish(
        "decision.made",
        {
            "decision": decision.to_event_payload(),
            "context": dict(event_context or {}),
        },
        payload_version=1,
    )


def reflect_action(
    hypotheses: list[ActionHypothesis],
    *,
    long_term_weight: float = 0.6,
    sandbox_weight: float = 0.25,
    resource_weight: float = 0.15,
    bus: EventBus | None = None,
    event_context: Mapping[str, Any] | None = None,
) -> ReflectionDecision:
    """Select the best action from candidate hypotheses.

    The returned decision keeps the legacy ``action``, ``decision_reason``,
    ``alternative_scores``, and ``ranked_actions`` fields while adding structured
    hypotheses, risks, benefits, confidence, and an action recommendation.
    """

    if not hypotheses:
        decision = ReflectionDecision(
            action=None,
            decision_reason="no hypothesis available",
            alternative_scores=[],
            ranked_actions=[],
            risks=["no candidate action was available to assess"],
            action_recommended="collect_more_hypotheses",
        )
        _publish_decision(decision, bus=bus, event_context=event_context)
        return decision

    scored = [
        (
            index,
            hyp,
            _hypothesis_score(
                hyp,
                long_term_weight=long_term_weight,
                sandbox_weight=sandbox_weight,
                resource_weight=resource_weight,
            ),
        )
        for index, hyp in enumerate(hypotheses)
    ]
    max_abs_score = max(abs(score) for _, _, score in scored) or 1.0
    assessments_by_action = {
        hyp.action: _assessment_for(hyp, score=score, max_abs_score=max_abs_score)
        for _, hyp, score in scored
    }
    scores = [(index, hyp.action, score) for index, hyp, score in scored]
    ranked_scores = sorted(scores, key=lambda entry: (-entry[2], entry[0]))
    ranked = [action for _, action, _ in ranked_scores]
    selected = ranked_scores[0][1]
    selected_assessment = assessments_by_action[selected]
    reason = (
        "selected highest weighted score "
        f"(long_term={long_term_weight:.2f}, sandbox={sandbox_weight:.2f}, "
        f"resources={resource_weight:.2f}); "
        f"confidence={selected_assessment.confidence:.2f}"
    )
    decision = ReflectionDecision(
        action=selected,
        decision_reason=reason,
        alternative_scores=ranked_scores,
        ranked_actions=ranked,
        hypotheses=selected_assessment.hypotheses,
        risks=selected_assessment.risks,
        benefits=selected_assessment.benefits,
        confidence=selected_assessment.confidence,
        action_recommended=selected_assessment.action_recommended,
        assessments=[assessments_by_action[action] for action in ranked],
    )
    _publish_decision(decision, bus=bus, event_context=event_context)
    return decision
