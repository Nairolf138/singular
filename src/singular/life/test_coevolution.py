"""Co-evolution primitives for living tests.

This module builds candidate tests from mutated skills and maintains a
small "living" test pool. The pool is intended to be lightweight and fully
deterministic when driven with a seeded ``random.Random`` instance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import random
from typing import Iterable

from . import sandbox


@dataclass(frozen=True)
class TestCandidate:
    """A single executable test expression."""

    expr: str
    origin: str = "mutation"


TestCandidate.__test__ = False


@dataclass
class LivingTestPool:
    """Mutable test pool with per-test liveness.

    ``ttl`` is decremented for tests that fail on the accepted code and those
    tests are evicted when it reaches ``0``.
    """

    tests: list[TestCandidate] = field(default_factory=list)
    ttl: dict[str, int] = field(default_factory=dict)
    max_size: int = 16
    initial_ttl: int = 3

    def _run_expr(self, code: str, expr: str) -> bool:
        probe = f"{code}\n__coevo_ok = 1 if ({expr}) else 0\nresult = __coevo_ok"
        try:
            out = sandbox.run(probe)
        except Exception:
            return False
        return bool(out)

    def evaluate(self, code: str) -> list[bool]:
        """Return pass/fail outcomes for all current tests."""

        return [self._run_expr(code, test.expr) for test in self.tests]

    def regression_detection_rate(self, base_code: str, mutated_code: str) -> float:
        """Measure how often tests catch a regression from ``base`` to ``mutated``."""

        if not self.tests:
            return 0.0
        base = self.evaluate(base_code)
        mutated = self.evaluate(mutated_code)
        detections = sum(1 for b, m in zip(base, mutated) if b and not m)
        return detections / len(self.tests)

    def evolve(
        self,
        accepted_code: str,
        candidates: Iterable[TestCandidate],
        rng: random.Random,
    ) -> dict[str, int]:
        """Evolve pool after acceptance and report added/removed counts."""

        added = 0
        removed = 0

        for candidate in candidates:
            if len(self.tests) >= self.max_size:
                idx = rng.randrange(len(self.tests))
                removed_test = self.tests.pop(idx)
                self.ttl.pop(removed_test.expr, None)
                removed += 1
            if candidate.expr in self.ttl:
                continue
            if self._run_expr(accepted_code, candidate.expr):
                self.tests.append(candidate)
                self.ttl[candidate.expr] = self.initial_ttl
                added += 1

        survivors: list[TestCandidate] = []
        for test in self.tests:
            passed = self._run_expr(accepted_code, test.expr)
            if passed:
                self.ttl[test.expr] = self.initial_ttl
                survivors.append(test)
                continue
            self.ttl[test.expr] = self.ttl.get(test.expr, self.initial_ttl) - 1
            if self.ttl[test.expr] > 0:
                survivors.append(test)
            else:
                self.ttl.pop(test.expr, None)
                removed += 1

        self.tests = survivors
        return {"added": added, "removed": removed}


def _extract_numeric_result(code: str) -> int | float | None:
    try:
        out = sandbox.run(code)
    except Exception:
        return None
    if isinstance(out, (int, float)):
        return out
    return None


def propose_test_candidates(
    mutated_code: str,
    rng: random.Random,
    limit: int = 3,
) -> list[TestCandidate]:
    """Propose deterministic test candidates from mutated skill behavior."""

    candidates = [
        TestCandidate("result == result", origin="sanity"),
        TestCandidate("abs(result - result) == 0", origin="shape"),
    ]

    observed = _extract_numeric_result(mutated_code)
    if observed is not None:
        candidates.append(TestCandidate(f"result == {observed!r}", origin="oracle"))
        candidates.append(TestCandidate(f"abs(result - ({observed!r})) <= 1", origin="tolerance"))

    rng.shuffle(candidates)
    return candidates[: max(0, limit)]
