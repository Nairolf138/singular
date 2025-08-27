from __future__ import annotations

import ast
import statistics
import time
from typing import Tuple

from . import sandbox


def score(code: str, runs: int = 5, alpha: float = 0.05) -> Tuple[float, float]:
    """Return performance score and variance for *code*.

    The code is executed ``runs`` times inside :mod:`life.sandbox`. For each
    execution the runtime in milliseconds is recorded. The median of these
    timings is combined with the AST node count as a simple complexity measure
    to produce the final score::

        score = median_ms + alpha * complexity

    The function returns a tuple ``(score, variance)`` where ``variance`` is the
    population variance of the collected timings. ``alpha`` controls the weight
    of the complexity penalty and defaults to ``0.05``.
    """

    timings = []
    for _ in range(runs):
        start = time.perf_counter()
        sandbox.run(code)
        timings.append((time.perf_counter() - start) * 1000)

    median_ms = statistics.median(timings)
    variance = statistics.pvariance(timings) if len(timings) > 1 else 0.0

    tree = ast.parse(code)
    complexity = sum(1 for _ in ast.walk(tree))

    score_value = median_ms + alpha * complexity
    return score_value, variance
