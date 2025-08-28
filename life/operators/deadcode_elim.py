from __future__ import annotations

import ast

# mypy: ignore-errors


class _DeadCodeElim(ast.NodeTransformer):
    """Eliminate obviously dead code such as ``if False`` blocks."""

    def visit_If(self, node: ast.If) -> ast.AST:  # pragma: no cover - delegating
        node = self.generic_visit(node)

        if isinstance(node.test, ast.Constant):
            return node.body if node.test.value else node.orelse

        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            if not node.orelse:
                return []
            new_test = ast.UnaryOp(op=ast.Not(), operand=node.test)
            new_node = ast.If(test=new_test, body=node.orelse, orelse=[])
            return ast.fix_missing_locations(new_node)

        if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.Pass):
            node.orelse = []

        return node


def apply(tree: ast.AST) -> ast.AST:
    """Return *tree* with trivial ``if`` statements removed."""

    new_tree = _DeadCodeElim().visit(tree)
    return ast.fix_missing_locations(new_tree)
