"""Utilities for evaluating target algorithms."""

from __future__ import annotations

import random
import statistics
import time
from typing import Callable, Dict, Iterable, List, Tuple


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


def diff_test(
    baseline: Callable[[Iterable[int]], int],
    variant: Callable[[Iterable[int]], int],
    cases: int = 1000,
) -> Dict[str, object]:
    """Perform diff-testing between ``baseline`` and ``variant``.

    Both functions are executed on the same randomly generated inputs. Any
    difference in returned value or raised exceptions is recorded. The
    function returns a dictionary describing whether the two implementations
    behaved identically and, if not, examples of the mismatches.

    Args:
        baseline: Reference implementation considered correct.
        variant: Alternative implementation to compare against ``baseline``.
        cases: Number of random test cases to execute.
    """

    mismatches: List[Dict[str, object]] = []
    for _ in range(cases):
        arr = [random.randint(-1000, 1000) for _ in range(random.randint(0, 100))]
        baseline_error = variant_error = None
        try:
            baseline_result = baseline(arr)
        except Exception as exc:
            baseline_error = exc
        try:
            variant_result = variant(arr)
        except Exception as exc:
            variant_error = exc

        if baseline_error or variant_error:
            mismatches.append(
                {
                    "input": arr,
                    "baseline_error": repr(baseline_error),
                    "variant_error": repr(variant_error),
                }
            )
            continue
        if baseline_result != variant_result:
            mismatches.append(
                {
                    "input": arr,
                    "baseline": baseline_result,
                    "variant": variant_result,
                }
            )

    return {
        "cases": cases,
        "mismatches": mismatches,
        "equivalent": not mismatches,
    }


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
