from __future__ import annotations

import ast
import importlib
import random
from typing import Callable, Dict, Mapping

from . import sandbox


class MutationValidationError(ValueError):
    """Raised when an operator produces an invalid transformed AST."""


def validate_transformed_ast(tree: ast.AST) -> ast.AST:
    """Validate a transformed AST before it enters sandbox scoring.

    The validation normalizes missing location metadata, verifies that the
    transformed tree can round-trip through ``unparse``/``parse``, and reuses
    the sandbox AST policy so rejected mutations are classified before runtime.
    """

    fixed = ast.fix_missing_locations(tree)
    try:
        round_tripped = ast.parse(ast.unparse(fixed))
    except (SyntaxError, ValueError, TypeError) as exc:
        raise MutationValidationError(f"invalid mutation syntax: {exc}") from exc
    try:
        sandbox._validate_ast(round_tripped)
    except sandbox.SandboxError as exc:
        raise MutationValidationError(f"invalid mutation rejected: {exc}") from exc
    return round_tripped


def invalid_mutation_rejection_source(reason: str) -> str:
    """Return safe source that sandbox scoring treats as a rejected mutation."""

    return f"__mutation_rejected_reason__ = {reason!r}"


def apply_mutation(
    code: str,
    operator: Callable[[ast.AST], ast.AST],
    rng: random.Random | None = None,
) -> str:
    """Run the mutation phase by transforming ``code`` with ``operator``."""

    tree = ast.parse(code)
    try:
        new_tree = operator(tree, rng=rng)
    except TypeError:
        new_tree = operator(tree)
    try:
        validated = validate_transformed_ast(new_tree)
    except MutationValidationError as exc:
        return invalid_mutation_rejection_source(str(exc))
    return ast.unparse(validated)


def _load_default_operators() -> Dict[str, Callable[[ast.AST], ast.AST]]:
    """Load mutation operators defined in :mod:`singular.life.operators`."""

    from . import operators as ops

    loaded: Dict[str, Callable[[ast.AST], ast.AST]] = {}
    for name in getattr(ops, "__all__", []):
        mod = importlib.import_module(f"singular.life.operators.{name}")
        loaded[name] = getattr(mod, "apply")
    return loaded


def select_operator(
    operators: Dict[str, Callable[[ast.AST], ast.AST]],
    stats: Dict[str, Dict[str, float]],
    policy: str,
    rng: random.Random,
    objective_bias: Mapping[str, float] | None = None,
) -> str:
    """Reflect on operator history and choose the next mutation strategy."""

    names = list(operators.keys())

    if policy == "analyze":
        return min(names, key=lambda n: stats[n]["count"])

    epsilon = {"exploit": 0.0, "explore": 1.0}.get(policy, 0.1)

    if rng.random() < epsilon or all(stats[n]["count"] == 0 for n in names):
        return rng.choice(names)

    def expected(name: str) -> float:
        s = stats[name]
        exploitation = s["reward"] / s["count"] if s["count"] else 0.0
        return exploitation + float((objective_bias or {}).get(name, 0.0))

    return max(names, key=expected)
