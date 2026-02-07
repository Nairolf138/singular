import ast

from singular.life.operators import eq_rewrite_reduce_sum


def test_reduce_sum_rewrites_loop():
    source = """
from typing import Iterable

def f(arr: Iterable[int]):
    total = 0
    for x in arr:
        total += x
    return total
"""
    expected = """
from typing import Iterable

def f(arr: Iterable[int]):
    total = sum(arr)
    return total
"""
    tree = ast.parse(source)
    new_tree = eq_rewrite_reduce_sum.apply(tree)
    assert ast.dump(new_tree, include_attributes=False) == ast.dump(
        ast.parse(expected), include_attributes=False
    )
