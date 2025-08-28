import ast
import random

from life.operators import const_tune


def test_const_tune_adjusts_small_ints():
    tree = ast.parse("a = 5\nb = 30")
    rng = random.Random(0)
    new_tree = const_tune.apply(tree, rng=rng, probability=1.0)
    code = ast.unparse(new_tree)
    assert "a = 6" in code
    assert "b = 30" in code
