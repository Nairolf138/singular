import ast

from life.operators import unrolling


def _dump(tree: ast.AST) -> str:
    return ast.dump(tree, include_attributes=False)


def test_unrolling_for_loop():
    source = """
def f():
    total = 0
    for i in range(3):
        total += i
    return total
"""
    expected = """
def f():
    total = 0
    i = 0
    total += i
    i = 1
    total += i
    i = 2
    total += i
    return total
"""
    tree = ast.parse(source)
    new_tree = unrolling.apply(tree)
    assert _dump(new_tree) == _dump(ast.parse(expected))
    compile(ast.unparse(new_tree), "<test>", "exec")


def test_unrolling_while_loop():
    source = """
def f():
    i = 0
    total = 0
    while i < 3:
        total += i
        i += 1
    return total
"""
    expected = """
def f():
    i = 0
    total = 0
    total += i
    i += 1
    total += i
    i += 1
    total += i
    i += 1
    return total
"""
    tree = ast.parse(source)
    new_tree = unrolling.apply(tree)
    assert _dump(new_tree) == _dump(ast.parse(expected))
    compile(ast.unparse(new_tree), "<test>", "exec")

