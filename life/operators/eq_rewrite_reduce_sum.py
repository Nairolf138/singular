from __future__ import annotations

import ast


class _ReduceSum(ast.NodeTransformer):
    """Rewrite simple accumulation loops into ``sum`` calls."""

    def _transform_body(self, body: list[ast.stmt]) -> list[ast.stmt]:
        new_body: list[ast.stmt] = []
        i = 0
        while i < len(body):
            stmt = body[i]
            if (
                i + 1 < len(body)
                and isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and isinstance(stmt.value, ast.Constant)
                and stmt.value.value == 0
            ):
                nxt = body[i + 1]
                if (
                    isinstance(nxt, ast.For)
                    and isinstance(nxt.target, ast.Name)
                    and not nxt.orelse
                    and len(nxt.body) == 1
                    and isinstance(nxt.body[0], ast.AugAssign)
                    and isinstance(nxt.body[0].op, ast.Add)
                    and isinstance(nxt.body[0].target, ast.Name)
                    and nxt.body[0].target.id == stmt.targets[0].id
                    and isinstance(nxt.body[0].value, ast.Name)
                    and nxt.body[0].value.id == nxt.target.id
                ):
                    sum_call = ast.Call(
                        func=ast.Name("sum", ast.Load()),
                        args=[nxt.iter],
                        keywords=[],
                    )
                    assign = ast.Assign(targets=[stmt.targets[0]], value=sum_call)
                    new_body.append(ast.copy_location(assign, stmt))
                    i += 2
                    continue
            new_body.append(self.visit(stmt))
            i += 1
        return new_body

    def visit_Module(self, node: ast.Module) -> ast.AST:  # pragma: no cover - delegating
        node.body = self._transform_body(node.body)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:  # pragma: no cover - delegating
        node.body = self._transform_body(node.body)
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:  # pragma: no cover - delegating
        node.body = self._transform_body(node.body)
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:  # pragma: no cover - delegating
        node.body = self._transform_body(node.body)
        return node

    def visit_For(self, node: ast.For) -> ast.AST:  # pragma: no cover - delegating
        node.body = self._transform_body(node.body)
        node.orelse = self._transform_body(node.orelse)
        return node

    def visit_While(self, node: ast.While) -> ast.AST:  # pragma: no cover - delegating
        node.body = self._transform_body(node.body)
        node.orelse = self._transform_body(node.orelse)
        return node

    def visit_If(self, node: ast.If) -> ast.AST:  # pragma: no cover - delegating
        node.body = self._transform_body(node.body)
        node.orelse = self._transform_body(node.orelse)
        return node

    def visit_With(self, node: ast.With) -> ast.AST:  # pragma: no cover - delegating
        node.body = self._transform_body(node.body)
        return node

    def visit_Try(self, node: ast.Try) -> ast.AST:  # pragma: no cover - delegating
        node.body = self._transform_body(node.body)
        node.orelse = self._transform_body(node.orelse)
        node.finalbody = self._transform_body(node.finalbody)
        for handler in node.handlers:
            handler.body = self._transform_body(handler.body)
        return node


def apply(tree: ast.AST) -> ast.AST:
    """Return *tree* with simple ``for``-accumulation loops replaced by ``sum``."""

    _ReduceSum().visit(tree)
    return ast.fix_missing_locations(tree)
