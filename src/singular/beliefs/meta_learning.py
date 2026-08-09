"""Meta-learning utilities to transform run outcomes into actionable beliefs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from typing import Iterable, Mapping

from .store import BeliefStore, _parse_datetime


@dataclass(frozen=True)
class RunFeatures:
    """Compact representation of context extracted from a mutation run.

    Extracted features are intentionally human-readable so stored beliefs can be
    audited later:
    - ``operator``: mutation strategy that was attempted.
    - ``failure_type``: normalized outcome class (sandbox error, rejected,
      improved, or neutral).
    - ``environment_signal``: coarse operational context (cold, stable, hot).
    - ``mood``: normalized cognitive/affective state.
    - ``outcome``: learning label used by probabilistic strategy rules.
    """

    operator: str
    failure_type: str
    environment_signal: str
    mood: str
    outcome: str
    extracted_features: dict[str, str] = field(default_factory=dict)
    learning_conditions: list[str] = field(default_factory=list)
    skill_family: str = "unknown"
    vital_state: str = "stable"
    objective: str = "unknown"
    governance_mode: str = "standard"
    candidate_characteristics: dict[str, str] = field(default_factory=dict)
    source_run_id: str | None = None

    def context_key(self) -> str:
        candidate = (
            ",".join(
                f"{key}={value}"
                for key, value in sorted(self.candidate_characteristics.items())
            )
            or "unknown"
        )
        return (
            f"failure={self.failure_type}|env={self.environment_signal}|"
            f"mood={self.mood}|outcome={self.outcome}|family={self.skill_family}|"
            f"vital={self.vital_state}|objective={self.objective}|"
            f"governance={self.governance_mode}|candidate={candidate}"
        )

    def feature_summary(self) -> dict[str, str]:
        """Return the documented feature map used by meta-learning."""

        if self.extracted_features:
            return dict(self.extracted_features)
        return {
            "operator": self.operator,
            "failure_type": self.failure_type,
            "environment_signal": self.environment_signal,
            "mood": self.mood,
            "outcome": self.outcome,
        }


@dataclass(frozen=True)
class StrategyRecommendation:
    """Operator recommendation inferred from past runs under similar contexts."""

    operator: str
    confidence: float
    context_key: str
    strategy_reason: str = ""
    supporting_features: dict[str, str] = field(default_factory=dict)
    learning_conditions: list[str] = field(default_factory=list)
    uncertainty: float = 1.0
    sample_count: int = 0
    regression_risk: float = 1.0
    recency: float = 0.0


def extract_run_features(
    *,
    operator: str,
    accepted: bool,
    base_score: float,
    mutated_score: float,
    temperature: float,
    mood: str | None,
    skill_family: str = "unknown",
    vital_state: str = "stable",
    objective: str = "unknown",
    governance_mode: str = "standard",
    candidate_characteristics: Mapping[str, str] | None = None,
    source_run_id: str | None = None,
) -> RunFeatures:
    """Extract stable run features for context-conditioned memory."""

    if mutated_score == float("-inf"):
        failure_type = "sandbox_error"
    elif not accepted:
        failure_type = "rejected"
    elif mutated_score < base_score:
        failure_type = "improved"
    else:
        failure_type = "neutral"

    if temperature <= 5.0:
        environment_signal = "cold"
    elif temperature >= 30.0:
        environment_signal = "hot"
    else:
        environment_signal = "stable"

    outcome = "success" if accepted else "failure"
    normalized_mood = (mood or "unknown").strip().lower() or "unknown"

    extracted_features = {
        "operator": operator,
        "failure_type": failure_type,
        "environment_signal": environment_signal,
        "mood": normalized_mood,
        "outcome": outcome,
        "score_delta": f"{mutated_score - base_score:.6f}",
        "accepted": str(bool(accepted)).lower(),
    }
    learning_conditions = [
        "persist when the run has an explicit acceptance label",
        "condition strategy confidence on failure, environment, mood, and outcome",
    ]
    if mutated_score == float("-inf"):
        learning_conditions.append("treat sandbox errors as high-risk failures")
    if abs(mutated_score - base_score) > 0.0:
        learning_conditions.append("include score delta as reward evidence")

    return RunFeatures(
        operator=operator,
        failure_type=failure_type,
        environment_signal=environment_signal,
        mood=normalized_mood,
        outcome=outcome,
        extracted_features=extracted_features,
        learning_conditions=learning_conditions,
        skill_family=skill_family,
        vital_state=vital_state,
        objective=objective,
        governance_mode=governance_mode,
        candidate_characteristics=dict(candidate_characteristics or {}),
        source_run_id=source_run_id,
    )


def register_run_result(
    store: BeliefStore,
    features: RunFeatures,
    *,
    reward_delta: float,
) -> None:
    """Persist probabilistic context -> strategy knowledge."""

    context = features.context_key()
    success = features.outcome == "success"
    documented_features = ",".join(
        f"{key}={value}" for key, value in sorted(features.feature_summary().items())
    )
    conditions = "|".join(features.learning_conditions)
    evidence = (
        f"features={documented_features};conditions={conditions};"
        f"reward={reward_delta:.6f}"
    )
    store.update_probabilistic_rule(
        context_key=context,
        strategy=features.operator,
        success=success,
        evidence=evidence,
        reward_delta=reward_delta,
        source_run_id=features.source_run_id,
    )
    anticipated_context = features.context_key().replace(
        f"failure={features.failure_type}", "failure=anticipated", 1
    )
    store.update_probabilistic_rule(
        context_key=anticipated_context,
        strategy=features.operator,
        success=success,
        evidence=evidence,
        reward_delta=reward_delta,
        source_run_id=features.source_run_id,
    )


def recommend_strategy(
    store: BeliefStore,
    *,
    failure_type: str,
    environment_signal: str,
    mood: str | None,
    outcome_hint: str,
    candidates: Iterable[str],
    skill_family: str = "unknown",
    vital_state: str = "stable",
    objective: str = "unknown",
    governance_mode: str = "standard",
    candidate_characteristics: Mapping[str, str] | None = None,
    minimum_samples: int = 3,
) -> StrategyRecommendation | None:
    """Return the highest-confidence strategy for the current context."""

    normalized_mood = (mood or "unknown").strip().lower() or "unknown"
    candidate_list = list(candidates)
    candidate = (
        ",".join(
            f"{key}={value}"
            for key, value in sorted((candidate_characteristics or {}).items())
        )
        or "unknown"
    )
    context_key = (
        f"failure={failure_type}|env={environment_signal}|"
        f"mood={normalized_mood}|outcome={outcome_hint}|family={skill_family}|"
        f"vital={vital_state}|objective={objective}|governance={governance_mode}|"
        f"candidate={candidate}"
    )
    ranked = store.recommend_strategies(
        context_key=context_key, candidates=candidate_list
    )
    if not ranked:
        return None
    # Rank on conservative confidence, not posterior mean: one lucky success
    # must never become strong evidence.
    assessed = []
    now = datetime.now(timezone.utc)
    for operator, posterior_mean in ranked:
        record = store._beliefs[f"strategy:{context_key}->{operator}"]
        samples = record.runs
        evidence_weight = samples / (samples + 2.0)
        confidence = posterior_mean * evidence_weight
        uncertainty = math.sqrt(
            (record.alpha * record.beta)
            / (((record.alpha + record.beta) ** 2) * (record.alpha + record.beta + 1.0))
        )
        age_days = max(
            0.0, (now - _parse_datetime(record.updated_at)).total_seconds() / 86400.0
        )
        recency = math.exp(-store.decay_per_day * age_days)
        regression_risk = record.beta / max(record.alpha + record.beta, 1e-9)
        assessed.append(
            (
                confidence,
                -regression_risk,
                operator,
                uncertainty,
                samples,
                regression_risk,
                recency,
            )
        )
    assessed.sort(reverse=True)
    confidence, _, best_operator, uncertainty, samples, regression_risk, recency = (
        assessed[0]
    )
    supporting_features = {
        "failure_type": failure_type,
        "environment_signal": environment_signal,
        "mood": normalized_mood,
        "outcome_hint": outcome_hint,
        "skill_family": skill_family,
        "vital_state": vital_state,
        "objective": objective,
        "governance_mode": governance_mode,
    }
    return StrategyRecommendation(
        operator=best_operator,
        confidence=confidence,
        context_key=context_key,
        strategy_reason=(
            f"highest stored confidence for {context_key} among "
            f"{', '.join(candidate_list)}"
        ),
        supporting_features=supporting_features,
        learning_conditions=[
            "recommend only strategies with existing probabilistic evidence",
            "rank candidates by decayed Bayesian confidence",
            f"require at least {minimum_samples} samples for operational preference",
        ],
        uncertainty=uncertainty,
        sample_count=samples,
        regression_risk=regression_risk,
        recency=recency,
    )
