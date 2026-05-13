"""High-level co-evolution flow for mutations and living tests.

This module centralizes the small primitives used by the life loop:
:class:`MapElites`, :class:`LivingTestPool`, and candidate generation.  The
``CoevolutionFlow`` interface keeps the mutation loop readable by grouping the
steps that belong together: propose candidate tests, evaluate a mutation against
living tests, compute robustness, expire/promote tests, and emit a single
decision object that callers can log.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import random
from typing import Iterable

from .map_elites import MapElites
from .test_coevolution import LivingTestPool, TestCandidate, propose_test_candidates


@dataclass(frozen=True)
class CoevolutionConfig:
    """Runtime knobs for mutation/test co-evolution."""

    enabled: bool = False
    robustness_weight: float = 1.0
    max_test_candidates: int = 3
    ttl: int = 3

    def normalized(self) -> "CoevolutionConfig":
        """Return a defensive, bounded copy suitable for execution."""

        return CoevolutionConfig(
            enabled=bool(self.enabled),
            robustness_weight=max(0.0, float(self.robustness_weight)),
            max_test_candidates=max(0, int(self.max_test_candidates)),
            ttl=max(1, int(self.ttl)),
        )


@dataclass(frozen=True)
class CandidateEvaluation:
    """Evaluation outcome for one proposed test candidate."""

    expr: str
    origin: str
    retained: bool


@dataclass(frozen=True)
class CoevolutionDecision:
    """Decision summary returned to the mutation loop and logger."""

    accepted: bool
    rejected_for_robustness: bool
    regression_detection_rate: float
    robustness_score: float
    score_combined_base: float
    score_combined_new: float
    proposed_tests: tuple[str, ...] = ()
    retained_tests: tuple[str, ...] = ()
    rejected_tests: tuple[str, ...] = ()
    tests_added: int = 0
    tests_removed: int = 0
    pool_size: int = 0


@dataclass
class CoevolutionFlow:
    """Coordinate living-test co-evolution for one mutation decision."""

    pool: LivingTestPool = field(default_factory=LivingTestPool)
    config: CoevolutionConfig = field(default_factory=CoevolutionConfig)

    def __post_init__(self) -> None:
        self.config = self.config.normalized()
        self.pool.initial_ttl = self.config.ttl

    def propose_candidates(
        self,
        mutated_code: str,
        rng: random.Random,
    ) -> list[TestCandidate]:
        """Generate bounded candidate tests from mutated behavior."""

        return propose_test_candidates(
            mutated_code,
            rng,
            limit=self.config.max_test_candidates,
        )

    def evaluate_against_mutation(self, base_code: str, mutated_code: str) -> float:
        """Return the living-test regression detection rate for a mutation."""

        return self.pool.regression_detection_rate(base_code, mutated_code)

    @staticmethod
    def robustness_from_detection_rate(detection_rate: float) -> float:
        """Convert regression detection pressure into a bounded robustness score."""

        return max(0.0, min(1.0, 1.0 - detection_rate))

    def expire_ttl(self, accepted_code: str) -> int:
        """Expire stale living tests against the currently accepted code."""

        before = len(self.pool.tests)
        self.pool.evolve(accepted_code, [], random.Random(0))
        return max(0, before - len(self.pool.tests))

    def promote_or_reject(
        self,
        accepted_code: str,
        candidates: Iterable[TestCandidate],
        rng: random.Random,
    ) -> tuple[dict[str, int], tuple[CandidateEvaluation, ...]]:
        """Promote passing candidates into the pool and report rejected tests."""

        candidate_list = list(candidates)
        before_exprs = {test.expr for test in self.pool.tests}
        delta = self.pool.evolve(accepted_code, candidate_list, rng)
        after_exprs = {test.expr for test in self.pool.tests}
        evaluations = tuple(
            CandidateEvaluation(
                expr=candidate.expr,
                origin=candidate.origin,
                retained=candidate.expr in after_exprs and candidate.expr not in before_exprs,
            )
            for candidate in candidate_list
        )
        return delta, evaluations

    def decide(
        self,
        *,
        base_code: str,
        mutated_code: str,
        base_score: float,
        mutated_score: float,
        initially_accepted: bool,
        rng: random.Random,
    ) -> CoevolutionDecision:
        """Evaluate, possibly reject, and evolve tests for a mutation."""

        detection_rate = self.evaluate_against_mutation(base_code, mutated_code)
        robustness_score = self.robustness_from_detection_rate(detection_rate)
        combined_base = base_score
        combined_new = mutated_score + (self.config.robustness_weight * detection_rate)
        accepted = initially_accepted and combined_new <= combined_base
        rejected_for_robustness = initially_accepted and not accepted

        proposed: list[TestCandidate] = []
        retained: tuple[str, ...] = ()
        rejected: tuple[str, ...] = ()
        delta = {"added": 0, "removed": 0}
        if accepted:
            proposed = self.propose_candidates(mutated_code, rng)
            delta, evaluations = self.promote_or_reject(mutated_code, proposed, rng)
            retained = tuple(item.expr for item in evaluations if item.retained)
            rejected = tuple(item.expr for item in evaluations if not item.retained)
        else:
            delta["removed"] = self.expire_ttl(base_code)

        return CoevolutionDecision(
            accepted=accepted,
            rejected_for_robustness=rejected_for_robustness,
            regression_detection_rate=detection_rate,
            robustness_score=robustness_score,
            score_combined_base=combined_base,
            score_combined_new=combined_new,
            proposed_tests=tuple(candidate.expr for candidate in proposed),
            retained_tests=retained,
            rejected_tests=rejected,
            tests_added=delta["added"],
            tests_removed=delta["removed"],
            pool_size=len(self.pool.tests),
        )


__all__ = [
    "CandidateEvaluation",
    "CoevolutionConfig",
    "CoevolutionDecision",
    "CoevolutionFlow",
    "MapElites",
    "LivingTestPool",
    "TestCandidate",
    "propose_test_candidates",
]
