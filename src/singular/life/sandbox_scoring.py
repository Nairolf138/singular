from __future__ import annotations

import ast
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from typing import ClassVar

from . import sandbox

CONFIRMED_ROOT_ESCAPE = "confirmed_root_escape"
OUTBOUND_SYMLINK = "outbound_symlink"
UNRESOLVED_PATH = "unresolved_path"
UNAUTHORIZED_INTERNAL_PATH = "unauthorized_internal_path"
MISSING_ARTIFACT = "missing_artifact"
INVALID_MUTATION = "invalid_mutation"


@dataclass(frozen=True)
class SandboxPathClassification:
    """Result of a filesystem-aware sandbox source check."""

    category: str | None
    requested_path: str
    resolved_path: str | None
    allowed_root: str | None
    rule: str

    @property
    def confirmed_escape(self) -> bool:
        return self.category in {CONFIRMED_ROOT_ESCAPE, OUTBOUND_SYMLINK}


def _is_within(path: Path, root: Path) -> bool:
    """Compare path components (not strings) to determine containment."""

    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def classify_source_sandbox_path(
    requested_path: str | Path,
    allowed_roots: Iterable[str | Path],
    *,
    sandbox_root: str | Path | None = None,
    require_exists: bool = True,
) -> SandboxPathClassification:
    """Classify a requested source path, including missing and symlink cases.

    Relative paths are interpreted from ``sandbox_root`` (or the current working
    directory).  A missing leaf is an absent artifact; a broken symlink or other
    strict-resolution failure is unresolved.  A lexical path inside an allowed
    root which resolves outside it is explicitly an outbound symlink.
    """

    requested = Path(requested_path)
    base = Path(sandbox_root) if sandbox_root is not None else Path.cwd()
    try:
        base_resolved = base.resolve(strict=True)
        roots = tuple(Path(root).resolve(strict=True) for root in allowed_roots)
    except (OSError, RuntimeError) as exc:
        return SandboxPathClassification(
            UNRESOLVED_PATH,
            str(requested),
            None,
            None,
            f"allowed_root_resolution_failed:{type(exc).__name__}",
        )
    lexical = requested if requested.is_absolute() else base_resolved / requested
    lexical = Path(os.path.abspath(lexical))
    lexical_root = next((root for root in roots if _is_within(lexical, root)), None)
    try:
        resolved = lexical.resolve(strict=False)
        if lexical.is_symlink() and not lexical.exists():
            lexical.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        return SandboxPathClassification(
            UNRESOLVED_PATH,
            str(requested),
            None,
            str(lexical_root) if lexical_root else None,
            f"path_resolution_failed:{type(exc).__name__}",
        )
    resolved_root = next((root for root in roots if _is_within(resolved, root)), None)
    if lexical_root is not None and resolved_root is None:
        return SandboxPathClassification(
            OUTBOUND_SYMLINK,
            str(requested),
            str(resolved),
            str(lexical_root),
            "symlink_target_outside_allowed_root",
        )
    if resolved_root is None:
        if _is_within(resolved, base_resolved):
            return SandboxPathClassification(
                UNAUTHORIZED_INTERNAL_PATH,
                str(requested),
                str(resolved),
                str(base_resolved),
                "path_inside_sandbox_but_outside_allowed_roots",
            )
        return SandboxPathClassification(
            CONFIRMED_ROOT_ESCAPE,
            str(requested),
            str(resolved),
            str(base_resolved),
            "resolved_path_outside_sandbox_root",
        )
    if require_exists and not resolved.exists():
        return SandboxPathClassification(
            MISSING_ARTIFACT,
            str(requested),
            str(resolved),
            str(resolved_root),
            "required_artifact_does_not_exist",
        )
    return SandboxPathClassification(
        None,
        str(requested),
        str(resolved),
        str(resolved_root),
        "resolved_path_within_allowed_root",
    )


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

    INFRASTRUCTURE_ERROR_TYPES: ClassVar[frozenset[str]] = frozenset(
        {
            "timeout",
            "sandbox_startup_timeout",
            "sandbox_worker_no_payload",
            "multiprocessing_error",
        }
    )
    CANDIDATE_ERROR_TYPES: ClassVar[frozenset[str]] = frozenset(
        {
            "syntax_error",
            "missing_result",
            "non_numeric_result",
            "non_finite_result",
            "forbidden_syntax",
            "forbidden_name",
            "sandbox_error",
            "runtime_exception",
        }
    )

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

    @property
    def is_infrastructure_failure(self) -> bool:
        """Whether the failure came from sandbox machinery rather than code."""

        return (not self.ok) and self.error_type in self.INFRASTRUCTURE_ERROR_TYPES

    @property
    def is_candidate_failure(self) -> bool:
        """Whether the candidate code executed invalidly in a healthy sandbox."""

        return (not self.ok) and not self.is_infrastructure_failure

    @property
    def comparable_score(self) -> float | None:
        """Score to use for business comparisons, or ``None`` if unavailable."""

        if not self.ok or not math.isfinite(float(self.score)):
            return None
        return float(self.score)


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
        return "source_invalid", "medium", False
    if mutation_failed:
        if _has_explicit_dangerous_pattern(mutated):
            return "invalid_mutation", "high", False
        return "invalid_mutation", "medium", False
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
        message = str(exception).lower()
        if "startup" in message or "did not start" in message:
            return "sandbox_startup_timeout"
        return "timeout"
    if isinstance(exception, SyntaxError):
        return "syntax_error"
    if isinstance(exception, sandbox.SandboxError):
        message = str(exception).lower()
        if "forbidden syntax" in message:
            return "forbidden_syntax"
        if "forbidden" in message and "use of" in message:
            return "forbidden_name"
        if "worker" in message and (
            "without payload" in message or "without returning" in message
        ):
            return "sandbox_worker_no_payload"
        if "multiprocessing method" in message or "multiprocessing" in message:
            return "multiprocessing_error"
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
