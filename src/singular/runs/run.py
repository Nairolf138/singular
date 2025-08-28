"""Run command implementation."""

from __future__ import annotations

import ast
import difflib
import random

from life.operators import const_tune, deadcode_elim, eq_rewrite_reduce_sum
from life.score import score

from ..psyche import Psyche
from ..memory import add_episode


def run(seed: int | None = None) -> str:
    """Generate a candidate mutation and return the winning code string.

    The operator used to mutate the base code is selected according to the
    current :class:`~singular.psyche.Psyche` ``mutation_policy``.  After scoring
    the base and mutated snippets a run record is fed back into
    :meth:`Psyche.process_run_record` so the psyche can adjust its mood and
    traits.

    Parameters
    ----------
    seed:
        Optional random seed for reproducibility.
    """

    base = (
        "total = 0\n"
        "for i in range(1000):\n"
        "    total += i\n"
        "result = total\n"
    )

    psyche = Psyche.load_state()
    policy = psyche.mutation_policy()

    tree = ast.parse(base)
    op_name = "eq_rewrite_reduce_sum"
    if policy == "explore":
        rng = random.Random(seed) if seed is not None else None
        mutated_tree = const_tune.apply(tree, rng=rng)
        op_name = "const_tune"
    elif policy == "analyze":
        mutated_tree = deadcode_elim.apply(tree)
        op_name = "deadcode_elim"
    else:  # "exploit" or any unknown policy
        mutated_tree = eq_rewrite_reduce_sum.apply(tree)

    mutated = ast.unparse(mutated_tree)

    alpha = 100.0
    base_score, _ = score(base, runs=1, alpha=alpha)
    mutated_score, _ = score(mutated, runs=1, alpha=alpha)

    # Derive runtime in milliseconds by subtracting the complexity penalty.
    complexity_base = sum(1 for _ in ast.walk(ast.parse(base)))
    ms_base = base_score - alpha * complexity_base
    complexity_new = sum(1 for _ in ast.walk(ast.parse(mutated)))
    ms_new = mutated_score - alpha * complexity_new

    record = {
        "skill": "demo",
        "op": op_name,
        "diff": "".join(
            difflib.unified_diff(
                base.splitlines(True), mutated.splitlines(True), fromfile="base", tofile="mutated"
            )
        ),
        "ok": True,
        "ms_base": ms_base,
        "ms_new": ms_new,
        "score_base": base_score,
        "score_new": mutated_score,
        "improved": mutated_score < base_score,
    }

    psyche.process_run_record(record)
    add_episode({"event": "mutation", **record, "mood": psyche.last_mood})
    psyche.save_state()

    return mutated if mutated_score <= base_score else base

