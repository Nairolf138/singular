"""Benchmark reduce_sum implementation."""

from __future__ import annotations

from graine.target.src.algorithms.reduce_sum import reduce_sum
from graine.target.src.evaluate import benchmark


def main() -> None:
    data = range(1000)
    # ``benchmark`` performs warm-up runs and pins the process to a single
    # logical CPU to reduce variance.
    results = benchmark(reduce_sum, data, cpu=0)
    median = results["median"]
    iqr = results["iqr"]
    low, high = results["ic95"]
    print(
        f"median: {median:.6f}s\n"
        f"IQR: {iqr:.6f}s\n"
        f"IC95: {low:.6f}s - {high:.6f}s"
    )


if __name__ == "__main__":
    main()
