import ast

from singular.life.operators import unrolling


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


def test_unrolling_unsupported_loop_left_intact():
    source = """
def f(items):
    total = 0
    for item in items:
        total += item
    return total
"""
    tree = ast.parse(source)
    new_tree = unrolling.apply(tree)
    assert _dump(new_tree) == _dump(ast.parse(source))
    compile(ast.unparse(new_tree), "<test>", "exec")


def test_unrolling_pipeline_rejects_invalid_output_without_circuit_breaker():
    from singular.life.mutation_flow import apply_mutation
    from singular.life.sandbox_scoring import (
        _sandbox_failure_category,
        score_code_with_error,
    )

    def forbidden_name_operator(tree: ast.AST) -> ast.AST:
        tree.body.append(
            ast.Assign(
                targets=[ast.Name(id="open", ctx=ast.Store())],
                value=ast.Constant(1),
            )
        )
        return tree

    mutated = apply_mutation("result = 1", forbidden_name_operator)
    result = score_code_with_error(mutated)

    assert "__mutation_rejected_reason__" in mutated
    assert result.is_candidate_failure
    assert _sandbox_failure_category(False, True, mutated) == (
        "invalid_mutation_rejected",
        "medium",
        False,
    )
