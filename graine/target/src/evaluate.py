"""Utilities for evaluating target algorithms."""

from __future__ import annotations

import random
import statistics
import time
from typing import Callable, Dict, Iterable, Tuple


def benchmark(
    func: Callable[[Iterable[int]], int],
    data: Iterable[int],
    runs: int = 21,
    bootstrap_samples: int = 1000,
) -> Dict[str, Tuple[float, float]]:
    """Return median runtime and 95% confidence interval.

    Args:
        func: Function to benchmark.
        data: Input iterable passed to ``func`` each run.
        runs: Number of timing runs to execute.
        bootstrap_samples: Number of bootstrap resamples for the CI.
    """
    timings = []
    payload = list(data)
    for _ in range(runs):
        start = time.perf_counter()
        func(payload)
        timings.append(time.perf_counter() - start)

    median = statistics.median(timings)
    boot = []
    for _ in range(bootstrap_samples):
        sample = random.choices(timings, k=len(timings))
        boot.append(statistics.median(sample))
    boot.sort()
    lower = boot[int(0.025 * len(boot))]
    upper = boot[int(0.975 * len(boot))]
    return {"median": median, "ic95": (lower, upper)}


def evaluate(candidate: Callable[[Iterable[int]], int]) -> Dict[str, object]:
    """Evaluate a candidate implementation of ``reduce_sum``.

    Returns functional correctness, performance metrics, and robustness.
    """
    # Functional correctness on a simple example
    sample = [1, 2, 3, 4, 5]
    functional = candidate(sample) == sum(sample)

    # Performance metrics
    performance = benchmark(candidate, range(1000))

    # Robustness checks
    robustness = True
    # Property: agreement with built-in sum for random lists
    for _ in range(10):
        arr = [random.randint(-1000, 1000) for _ in range(random.randint(0, 100))]
        if candidate(arr) != sum(arr):
            robustness = False
            break
    # Metamorphic: permutation invariance
    if robustness:
        arr = [random.randint(-1000, 1000) for _ in range(50)]
        shuffled = arr.copy()
        random.shuffle(shuffled)
        robustness = candidate(arr) == candidate(shuffled)

    return {
        "functional": functional,
        "performance": performance,
        "robustness": robustness,
    }
