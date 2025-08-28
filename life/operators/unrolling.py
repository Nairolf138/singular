"""Loop unrolling operator.

This operator performs a very small amount of static analysis in order to
replace tiny ``for`` or ``while`` loops with a straight‑line sequence of their
body.  Only loops with a statically known number of iterations are handled and
``else`` blocks are ignored.
"""

from __future__ import annotations

import ast
import copy
import random
from typing import Iterable

# mypy: ignore-errors


_UNROLL_LIMIT = 5


class _Unroll(ast.NodeTransformer):
    """Unroll small ``for``/``while`` loops."""

    # ------------------------------------------------------------------
    # Utility helpers
    def _iter_values(self, node: ast.Call) -> list[int] | None:
        if not (
            isinstance(node.func, ast.Name)
            and node.func.id == "range"
            and not node.keywords
        ):
            return None
        try:
            args = [ast.literal_eval(a) for a in node.args]
        except Exception:  # pragma: no cover - defensive
            return None
        values = list(range(*args))
        if 0 < len(values) <= _UNROLL_LIMIT:
            return values
        return None

    # ------------------------------------------------------------------
    # ``for`` loop handling
    def _unroll_for(self, node: ast.For) -> list[ast.stmt] | None:
        if node.orelse:
            return None
        if not isinstance(node.target, ast.Name):
            return None
        if not isinstance(node.iter, ast.Call):
            return None

        values = self._iter_values(node.iter)
        if values is None:
            return None

        new_body: list[ast.stmt] = []
        for val in values:
            assign = ast.Assign(
                targets=[copy.deepcopy(node.target)],
                value=ast.Constant(val),
            )
            new_body.append(ast.copy_location(assign, node))
            for stmt in node.body:
                new_body.append(self.visit(copy.deepcopy(stmt)))
        return new_body

    # ------------------------------------------------------------------
    # ``while`` loop handling
    def _unroll_while(
        self, node: ast.While, prior: list[ast.stmt]
    ) -> list[ast.stmt] | None:
        if node.orelse:
            return None

        test = node.test
        if not (
            isinstance(test, ast.Compare)
            and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Lt)
            and isinstance(test.left, ast.Name)
            and len(test.comparators) == 1
            and isinstance(test.comparators[0], ast.Constant)
        ):
            return None
        var = test.left.id
        try:
            stop = int(test.comparators[0].value)
        except Exception:  # pragma: no cover - defensive
            return None

        assign = None
        for stmt in reversed(prior):
            if (
                isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and stmt.targets[0].id == var
                and isinstance(stmt.value, ast.Constant)
            ):
                assign = stmt
                break
        if assign is None:
            return None
        try:
            start = int(assign.value.value)
        except Exception:  # pragma: no cover - defensive
            return None

        if not node.body:
            return None
        last = node.body[-1]
        if not (
            isinstance(last, ast.AugAssign)
            and isinstance(last.op, ast.Add)
            and isinstance(last.target, ast.Name)
            and last.target.id == var
            and isinstance(last.value, ast.Constant)
            and last.value.value == 1
        ):
            return None

        iterations = stop - start
        if iterations <= 0 or iterations > _UNROLL_LIMIT:
            return None

        new_body: list[ast.stmt] = []
        for _ in range(iterations):
            for stmt in node.body:
                new_body.append(self.visit(copy.deepcopy(stmt)))
        return new_body

    # ------------------------------------------------------------------
    # Body transformation driver
    def _transform_body(self, body: list[ast.stmt]) -> list[ast.stmt]:
        new_body: list[ast.stmt] = []
        for stmt in body:
            if isinstance(stmt, ast.For):
                unrolled = self._unroll_for(stmt)
                if unrolled is not None:
                    new_body.extend(unrolled)
                    continue
                new_body.append(self.visit(stmt))
            elif isinstance(stmt, ast.While):
                unrolled = self._unroll_while(stmt, new_body)
                if unrolled is not None:
                    new_body.extend(unrolled)
                    continue
                new_body.append(self.visit(stmt))
            else:
                new_body.append(self.visit(stmt))
        return new_body

    # ------------------------------------------------------------------
    # ``ast.NodeTransformer`` hooks delegating to ``_transform_body``
    def visit_Module(
        self, node: ast.Module
    ) -> ast.AST:  # pragma: no cover - delegating
        node.body = self._transform_body(node.body)
        return node

    def visit_FunctionDef(
        self, node: ast.FunctionDef
    ) -> ast.AST:  # pragma: no cover - delegating
        node.body = self._transform_body(node.body)
        return node

    def visit_AsyncFunctionDef(
        self, node: ast.AsyncFunctionDef
    ) -> ast.AST:  # pragma: no cover - delegating
        node.body = self._transform_body(node.body)
        return node

    def visit_ClassDef(
        self, node: ast.ClassDef
    ) -> ast.AST:  # pragma: no cover - delegating
        node.body = self._transform_body(node.body)
        return node

    def visit_For(self, node: ast.For) -> ast.AST:  # pragma: no cover - delegating
        node.body = self._transform_body(node.body)
        node.orelse = self._transform_body(node.orelse)
        return node

    def visit_While(
        self, node: ast.While
    ) -> ast.AST:  # pragma: no cover - delegating
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


def apply(tree: ast.AST, rng: random.Random | None = None) -> ast.AST:
    """Return *tree* with small loops unrolled."""

    _Unroll().visit(tree)
    return ast.fix_missing_locations(tree)

