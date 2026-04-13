"""Meta-learning utilities to transform run outcomes into actionable beliefs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .store import BeliefStore


@dataclass(frozen=True)
class RunFeatures:
    """Compact representation of context extracted from a mutation run."""

    operator: str
    failure_type: str
    environment_signal: str
    mood: str
    outcome: str

    def context_key(self) -> str:
        return (
            f"failure={self.failure_type}|env={self.environment_signal}|"
            f"mood={self.mood}|outcome={self.outcome}"
        )


@dataclass(frozen=True)
class StrategyRecommendation:
    """Operator recommendation inferred from past runs under similar contexts."""

    operator: str
    confidence: float
    context_key: str


def extract_run_features(
    *,
    operator: str,
    accepted: bool,
    base_score: float,
    mutated_score: float,
    temperature: float,
    mood: str | None,
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

    return RunFeatures(
        operator=operator,
        failure_type=failure_type,
        environment_signal=environment_signal,
        mood=normalized_mood,
        outcome=outcome,
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
    evidence = (
        f"operator={features.operator};failure={features.failure_type};"
        f"env={features.environment_signal};mood={features.mood};"
        f"outcome={features.outcome};reward={reward_delta:.6f}"
    )
    store.update_probabilistic_rule(
        context_key=context,
        strategy=features.operator,
        success=success,
        evidence=evidence,
        reward_delta=reward_delta,
    )
    anticipated_context = (
        f"failure=anticipated|env={features.environment_signal}|"
        f"mood={features.mood}|outcome={features.outcome}"
    )
    store.update_probabilistic_rule(
        context_key=anticipated_context,
        strategy=features.operator,
        success=success,
        evidence=evidence,
        reward_delta=reward_delta,
    )


def recommend_strategy(
    store: BeliefStore,
    *,
    failure_type: str,
    environment_signal: str,
    mood: str | None,
    outcome_hint: str,
    candidates: Iterable[str],
) -> StrategyRecommendation | None:
    """Return the highest-confidence strategy for the current context."""

    normalized_mood = (mood or "unknown").strip().lower() or "unknown"
    context_key = (
        f"failure={failure_type}|env={environment_signal}|"
        f"mood={normalized_mood}|outcome={outcome_hint}"
    )
    ranked = store.recommend_strategies(context_key=context_key, candidates=candidates)
    if not ranked:
        return None
    best_operator, confidence = ranked[0]
    return StrategyRecommendation(
        operator=best_operator,
        confidence=confidence,
        context_key=context_key,
    )
