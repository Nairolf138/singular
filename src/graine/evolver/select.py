"""Selection utilities implementing a minimal NSGA-II algorithm.

The selection process accepts at most a single patch per cycle. All other
candidates are rejected and the reasons for acceptance or rejection are
logged. A conservative elitism strategy ensures that a previous elite patch
is retained unless dominated by a newcomer. Candidates that do not satisfy
all required thresholds (tests, performance, quality and stability) are
rejected before the multi-objective selection is performed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List
import logging

from .dsl import Patch

logger = logging.getLogger(__name__)


@dataclass(eq=False)
class Candidate:
    """Container for a patch and its objective values.

    Each candidate also records whether it satisfies a number of thresholds
    (typically ``tests``, ``perf``, ``quality`` and ``stability``). Candidates
    failing any threshold are ignored by :func:`select`.
    """

    patch: Patch
    objectives: Dict[str, float]
    thresholds: Dict[str, bool] | None = None
    name: str = ""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name or repr(self.patch)

    def meets_thresholds(self) -> bool:
        """Return ``True`` if all threshold checks are satisfied."""

        return all(self.thresholds.values()) if self.thresholds else True


def dominates(a: Candidate, b: Candidate) -> bool:
    """Return ``True`` if candidate ``a`` dominates ``b`` (all objectives are
    less than or equal and at least one is strictly less)."""

    better_or_equal = all(a.objectives[m] <= b.objectives[m] for m in a.objectives)
    strictly_better = any(a.objectives[m] < b.objectives[m] for m in a.objectives)
    return better_or_equal and strictly_better


def fast_non_dominated_sort(population: List[Candidate]) -> List[List[Candidate]]:
    """Classical fast non-dominated sort used by NSGA-II."""

    fronts: List[List[Candidate]] = []
    S: Dict[Candidate, List[Candidate]] = {}
    n: Dict[Candidate, int] = {}
    rank: Dict[Candidate, int] = {}

    for p in population:
        S[p] = []
        n[p] = 0
        for q in population:
            if p is q:
                continue
            if dominates(p, q):
                S[p].append(q)
            elif dominates(q, p):
                n[p] += 1
        if n[p] == 0:
            rank[p] = 0
    current_front = [p for p in population if n[p] == 0]
    fronts.append(current_front)
    i = 0
    while fronts[i]:
        next_front: List[Candidate] = []
        for p in fronts[i]:
            for q in S[p]:
                n[q] -= 1
                if n[q] == 0:
                    rank[q] = i + 1
                    next_front.append(q)
        i += 1
        fronts.append(next_front)
    return fronts[:-1]


def crowding_distance(front: List[Candidate]) -> Dict[Candidate, float]:
    """Compute crowding distance for a single front."""

    distance = {c: 0.0 for c in front}
    if not front:
        return distance
    objectives = list(front[0].objectives.keys())
    for m in objectives:
        front.sort(key=lambda c: c.objectives[m])
        distance[front[0]] = float("inf")
        distance[front[-1]] = float("inf")
        min_m = front[0].objectives[m]
        max_m = front[-1].objectives[m]
        denom = max_m - min_m or 1.0
        for i in range(1, len(front) - 1):
            prev_m = front[i - 1].objectives[m]
            next_m = front[i + 1].objectives[m]
            distance[front[i]] += (next_m - prev_m) / denom
    return distance


def select(
    candidates: List[Candidate], prev_best: Candidate | None = None
) -> Candidate | None:
    """Select at most one candidate using NSGA-II with conservative elitism."""

    # First discard candidates that fail any of the required thresholds. These
    # are never eligible for selection.
    feasible: List[Candidate] = []
    for cand in candidates:
        if cand.meets_thresholds():
            feasible.append(cand)
        else:
            logger.info("Rejected patch %s: failed thresholds", cand)

    elite = prev_best if prev_best and prev_best.meets_thresholds() else None
    if prev_best and elite is None:
        logger.info("Rejected patch %s: failed thresholds", prev_best)

    if not feasible and elite is None:
        return None

    # Conservative elitism: retain previous best if no feasible candidate
    # dominates it.
    if elite and not any(dominates(c, elite) for c in feasible):
        logger.info("Accepted patch %s", elite)
        for cand in feasible:
            reason = (
                "dominated by accepted patch"
                if dominates(elite, cand)
                else "crowded out"
            )
            logger.info("Rejected patch %s: %s", cand, reason)
        return elite

    population = feasible + ([elite] if elite else [])
    fronts = fast_non_dominated_sort(population)
    first_front = fronts[0]
    cd = crowding_distance(first_front)
    first_front.sort(key=lambda c: cd[c], reverse=True)
    chosen = first_front[0]

    # Logging and enforcing single acceptance
    for cand in feasible:
        if cand is chosen:
            logger.info("Accepted patch %s", cand)
        else:
            reason = (
                "dominated by accepted patch"
                if dominates(chosen, cand)
                else "crowded out"
            )
            logger.info("Rejected patch %s: %s", cand, reason)
    if elite is not None:
        if chosen is elite:
            logger.info("Accepted patch %s: retained as elite", elite)
        else:
            reason = (
                "dominated by accepted patch"
                if dominates(chosen, elite)
                else "crowded out"
            )
            logger.info("Rejected patch %s: %s", elite, reason)
    return chosen
