"""Utilities for evaluating target algorithms."""

from __future__ import annotations

import gc
import os
import random
import statistics
import time
from typing import Callable, Dict, Iterable, List, Tuple


def benchmark(
    func: Callable[[Iterable[int]], int],
    data: Iterable[int],
    runs: int = 21,
    warmups: int = 5,
    bootstrap_samples: int = 1000,
    cpu: int | None = 0,
) -> Dict[str, Tuple[float, float]]:
    """Return benchmark statistics for ``func``.

    The function performs a configurable number of warm-up runs before
    measuring ``runs`` executions. During measurement the process is pinned to
    a single logical CPU if possible to reduce variance. The median runtime,
    interquartile range (IQR) and a 95% confidence interval for the median are
    reported.

    Args:
        func: Function to benchmark.
        data: Input iterable passed to ``func`` each run.
        runs: Number of timing runs to execute.
        warmups: Warm-up iterations executed before timing.
        bootstrap_samples: Number of bootstrap resamples for the CI.
        cpu: Logical CPU to pin to. ``None`` disables pinning.
    """

    payload = list(data)

    # Optionally pin to a specific CPU to limit scheduling variance.
    original_affinity = None
    if cpu is not None:
        try:
            original_affinity = os.sched_getaffinity(0)
            os.sched_setaffinity(0, {cpu})
        except (AttributeError, PermissionError, OSError):
            original_affinity = None

    try:
        # Warm-up runs to prime caches and JITs if any.
        for _ in range(warmups):
            func(payload)

        timings = []
        gc.collect()
        gc.disable()
        for _ in range(runs):
            start = time.perf_counter()
            func(payload)
            timings.append(time.perf_counter() - start)
        gc.enable()
    finally:
        if original_affinity is not None:
            try:
                os.sched_setaffinity(0, original_affinity)
            except (AttributeError, PermissionError, OSError):
                pass

    median = statistics.median(timings)
    quartiles = statistics.quantiles(timings, n=4)
    q1, q3 = quartiles[0], quartiles[2]
    iqr = q3 - q1

    boot = []
    for _ in range(bootstrap_samples):
        sample = random.choices(timings, k=len(timings))
        boot.append(statistics.median(sample))
    boot.sort()
    lower = boot[int(0.025 * len(boot))]
    upper = boot[int(0.975 * len(boot))]
    return {"median": median, "iqr": iqr, "ic95": (lower, upper)}


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
