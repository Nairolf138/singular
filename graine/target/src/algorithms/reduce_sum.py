"""Example target module."""

from typing import Iterable


def reduce_sum(values: Iterable[int]) -> int:
    """Return the sum of the iterable."""
    acc = 0
    for v in values:
        acc += v
    return acc
