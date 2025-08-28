"""Run command implementation."""

from __future__ import annotations

import ast

from life.operators.eq_rewrite_reduce_sum import apply
from life.score import score


def run(seed: int | None = None) -> str:
    """Generate a candidate mutation and return the winning code string.

    This is a very small demo that mutates a naive accumulation loop into a
    ``sum`` call using :mod:`life.operators.eq_rewrite_reduce_sum`. Both the
    original and mutated versions are scored via :func:`life.score.score` with a
    strong complexity penalty so that the simpler variant wins deterministically.
    The function returns the code snippet with the better score.

    Parameters
    ----------
    seed:
        Optional random seed for reproducibility. (Currently unused.)
    """

    base = (
        "total = 0\n"
        "for i in range(1000):\n"
        "    total += i\n"
        "result = total\n"
    )

    tree = ast.parse(base)
    mutated_tree = apply(tree)
    mutated = ast.unparse(mutated_tree)

    base_score, _ = score(base, runs=1, alpha=100.0)
    mutated_score, _ = score(mutated, runs=1, alpha=100.0)

    return mutated if mutated_score <= base_score else base
