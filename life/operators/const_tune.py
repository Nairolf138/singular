from __future__ import annotations

import ast
import random

# mypy: ignore-errors


class _ConstTune(ast.NodeTransformer):
    """Randomly adjust small integer constants by ±1."""

    def __init__(self, rng: random.Random, probability: float) -> None:
        self.rng = rng
        self.probability = probability

    def visit_Constant(
        self, node: ast.Constant
    ) -> ast.AST:  # pragma: no cover - trivial
        if isinstance(node.value, int) and -16 <= node.value <= 16:
            if self.rng.random() < self.probability:
                delta = self.rng.choice([-1, 1])
                return ast.copy_location(ast.Constant(node.value + delta), node)
        return node


def apply(
    tree: ast.AST,
    rng: random.Random | None = None,
    probability: float = 0.5,
) -> ast.AST:
    """Tune integer constants within ``[-16, 16]`` by one with given probability."""

    rng = rng or random
    _ConstTune(rng, probability).visit(tree)
    return ast.fix_missing_locations(tree)
