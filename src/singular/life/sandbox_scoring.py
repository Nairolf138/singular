from __future__ import annotations

import ast
import math
from dataclasses import dataclass

from . import sandbox


@dataclass(init=False, frozen=True)
class SandboxScore:
    """Structured sandbox scoring outcome.

    ``score`` keeps the historical algorithmic contract: failed sandbox scoring
    yields ``-inf``.  ``ok`` and the error fields carry diagnostics so callers
    can distinguish a failing source from a failing mutation without parsing the
    score itself.
    """

    score: float
    ok: bool
    error_type: str | None
    error_message: str | None
    _legacy_exception_type: str | None

    def __init__(
        self,
        score: float,
        ok: bool = True,
        error_type: str | None = None,
        error_message: str | None = None,
        *,
        failed: bool | None = None,
        error_reason: str | None = None,
        exception_type: str | None = None,
        exception_message: str | None = None,
    ) -> None:
        """Create a score result, accepting legacy keyword names."""

        if failed is not None:
            ok = not failed
        resolved_error_type = error_type or error_reason
        resolved_error_message = error_message or exception_message
        if resolved_error_message is None and exception_type is not None:
            resolved_error_message = exception_type
        object.__setattr__(self, "score", score)
        object.__setattr__(self, "ok", ok)
        object.__setattr__(self, "error_type", resolved_error_type)
        object.__setattr__(self, "error_message", resolved_error_message)
        object.__setattr__(self, "_legacy_exception_type", exception_type)

    @property
    def failed(self) -> bool:
        """Backward-compatible inverse of ``ok``."""

        return not self.ok

    @property
    def error_reason(self) -> str | None:
        """Backward-compatible alias for ``error_type``."""

        return self.error_type

    @property
    def exception_type(self) -> str | None:
        """Best-effort legacy exception type derived from ``error_type``."""

        if self._legacy_exception_type is not None:
            return self._legacy_exception_type
        if self.error_type == "runtime_exception" and self.error_message:
            return self.error_message.split(":", 1)[0]
        return self.error_type

    @property
    def exception_message(self) -> str | None:
        """Backward-compatible alias for ``error_message``."""

        return self.error_message


DANGEROUS_MUTATION_NAMES = frozenset(
    {
        "open",
        "exec",
        "eval",
        "compile",
        "__import__",
        "input",
        "os",
        "sys",
        "socket",
        "subprocess",
    }
)


def _has_explicit_dangerous_pattern(code: str) -> bool:
    """Return True when code explicitly references dangerous capabilities."""

    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in DANGEROUS_MUTATION_NAMES:
            return True
        if isinstance(node, ast.Attribute) and node.attr in DANGEROUS_MUTATION_NAMES:
            return True
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name.split(".", 1)[0] for alias in node.names]
            module = []
            if isinstance(node, ast.ImportFrom) and node.module:
                module.append(node.module.split(".", 1)[0])
            if any(name in DANGEROUS_MUTATION_NAMES for name in [*names, *module]):
                return True
    return False


def _sandbox_failure_category(
    base_failed: bool, mutation_failed: bool, mutated: str
) -> tuple[str | None, str | None, bool]:
    """Classify sandbox failures for governance escalation."""

    if base_failed:
        return "source_sandbox_violation", "critical", True
    if mutation_failed:
        if _has_explicit_dangerous_pattern(mutated):
            return "dangerous_mutation_violation", "critical", True
        return "invalid_mutation_rejected", "medium", False
    return None, None, False


def _score_failure(
    error_type: str,
    exception: BaseException | None = None,
    *,
    message: str | None = None,
) -> SandboxScore:
    """Build a failed scoring result with a human-readable message."""

    exception_type = type(exception).__name__ if exception is not None else None
    if message is None and exception is not None:
        message = f"{exception_type}: {exception}"
    return SandboxScore(
        score=float("-inf"),
        ok=False,
        error_type=error_type,
        error_message=message,
        exception_type=exception_type,
    )


def _classify_score_exception(exception: BaseException) -> str:
    """Map sandbox exceptions to stable diagnostic categories."""

    if isinstance(exception, TimeoutError):
        return "timeout"
    if isinstance(exception, SyntaxError):
        return "syntax_error"
    if isinstance(exception, sandbox.SandboxError):
        message = str(exception).lower()
        if "result" in message and ("missing" in message or "did not set" in message):
            return "missing_result"
        return "sandbox_error"
    return "runtime_exception"


def score_code_with_error(code: str) -> SandboxScore:
    """Execute ``code`` in the sandbox and return score plus failure details.

    Failure reasons are intentionally stable for diagnostics: forbidden syntax,
    forbidden names, timeout, runtime exception, non-numeric result, or non-finite
    result.
    """

    try:
        result = sandbox.run(code)
    except Exception as exc:
        return _score_failure(_classify_score_exception(exc), exc)
    if result is None:
        return _score_failure(
            "missing_result",
            message="sandbox code did not set a numeric result",
        )
    if not isinstance(result, (int, float)):
        return _score_failure(
            "non_numeric_result",
            message=f"sandbox result is not numeric (type: {type(result).__name__})",
        )
    score = float(result)
    if not math.isfinite(score):
        return _score_failure("non_finite_result", message=f"sandbox result is {score}")
    return SandboxScore(score=score)


def score_code(code: str) -> float:
    """Execute ``code`` in the sandbox and return a numeric score.

    Non-numeric or failing executions yield ``-inf``.
    """

    return score_code_with_error(code).score
