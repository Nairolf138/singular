import ast

from life.operators import deadcode_elim


def test_deadcode_elim_removes_trivial_ifs():
    source = """
def f(x):
    if False:
        x += 1
    if True:
        x += 2
    if x > 0:
        pass
    else:
        x -= 1
    if x < 0:
        x += 3
    else:
        pass
    return x
"""
    expected = """
def f(x):
    x += 2
    if not (x > 0):
        x -= 1
    if x < 0:
        x += 3
    return x
"""
    tree = ast.parse(source)
    new_tree = deadcode_elim.apply(tree)
    assert ast.dump(new_tree, include_attributes=False) == ast.dump(
        ast.parse(expected), include_attributes=False
    )
