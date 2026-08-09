"""Validation helpers for generated skills before publication."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, Sequence

from . import sandbox


@dataclass(frozen=True)
class SkillValidationResult:
    """Structured result for pre-publication skill validation."""

    ok: bool
    reason: str = "validated"


def _function_returns_only_none(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    returns = [node for node in ast.walk(func) if isinstance(node, ast.Return)]
    if not returns:
        return True
    return all(
        ret.value is None
        or (isinstance(ret.value, ast.Constant) and ret.value.value is None)
        for ret in returns
    )


def _has_expected_function(
    tree: ast.AST, expected_symbol: str
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in getattr(tree, "body", []):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == expected_symbol
        ):
            return node
    return None


def validate_generated_skill(
    code: str,
    *,
    expected_symbol: str,
    examples: Sequence[tuple[Sequence[Any], Any]] = (),
    timeout: float | None = None,
) -> SkillValidationResult:
    """Validate generated skill source before it can enter the active catalog."""

    if not code.strip():
        return SkillValidationResult(False, "empty scaffold")
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return SkillValidationResult(False, f"syntax error: {exc.msg}")

    functions = [
        node
        for node in getattr(tree, "body", [])
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    if not functions:
        return SkillValidationResult(False, "generated skill defines no function")

    expected = _has_expected_function(tree, expected_symbol)
    if expected is None:
        return SkillValidationResult(
            False, f"missing expected skill symbol: {expected_symbol}"
        )
    if _function_returns_only_none(expected):
        return SkillValidationResult(
            False, f"skill symbol {expected_symbol} only returns None"
        )

    if not examples:
        try:
            observed = sandbox.run(
                f"{code}\nresult = {expected_symbol}()", timeout=timeout
            )
        except Exception as exc:
            return SkillValidationResult(
                False, f"minimal sandbox validation failed: {exc}"
            )
        if observed is None:
            return SkillValidationResult(
                False,
                f"skill symbol {expected_symbol} returned None for minimal invocation",
            )

    for inputs, output in examples:
        args = ", ".join(repr(value) for value in inputs)
        test = f"{code}\nresult = {expected_symbol}({args})"
        try:
            observed = sandbox.run(test, timeout=timeout)
        except Exception as exc:
            return SkillValidationResult(
                False, f"example sandbox validation failed: {exc}"
            )
        if observed != output:
            return SkillValidationResult(
                False, f"example mismatch: expected {output!r}, got {observed!r}"
            )

    return SkillValidationResult(True)
