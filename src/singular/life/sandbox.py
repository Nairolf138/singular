"""Restricted sandbox execution environment."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import logging
import multiprocessing
import os
import queue as queue_module
import sys
import tempfile
from types import ModuleType
from typing import Any, Dict

resource_module: ModuleType | None
try:
    import resource as resource_module
except ImportError:  # pragma: no cover - Windows or unsupported platforms
    resource_module = None


logger = logging.getLogger(__name__)


ALLOWED_BUILTINS = {
    "abs": abs,
    "min": min,
    "max": max,
    "range": range,
    "len": len,
    "sum": sum,
    "all": all,
    "any": any,
}

FORBIDDEN_NAMES = {
    "open",
    "exec",
    "eval",
    "compile",
    "__import__",
    "input",
    # Block access to common system modules even if provided
    "os",
    "sys",
    "socket",
    "subprocess",
}

FORBIDDEN_NODES = (
    ast.Import,
    ast.ImportFrom,
    ast.With,
    ast.AsyncWith,
)

DEFAULT_TIMEOUT_S = 3.0
MIN_TIMEOUT_S = 0.05
DEFAULT_STARTUP_GRACE_S = 2.0
DEFAULT_MEMORY_LIMIT = 256 * 1024 * 1024
SANDBOX_TIMEOUT_ENV = "SINGULAR_SANDBOX_TIMEOUT"
SANDBOX_STARTUP_GRACE_ENV = "SINGULAR_SANDBOX_STARTUP_GRACE"
SANDBOX_MEMORY_LIMIT_ENV = "SINGULAR_SANDBOX_MEMORY_LIMIT"
SANDBOX_MP_METHOD_ENV = "SINGULAR_SANDBOX_MP_METHOD"


@dataclass(frozen=True)
class SandboxConfig:
    """Centralized sandbox process/resource configuration."""

    execution_timeout_s: float = DEFAULT_TIMEOUT_S
    startup_grace_s: float = DEFAULT_STARTUP_GRACE_S
    min_timeout_s: float = MIN_TIMEOUT_S
    memory_limit: int = DEFAULT_MEMORY_LIMIT
    multiprocessing_method: str | None = None

    @classmethod
    def from_environment(
        cls,
        *,
        timeout: float | None = None,
        memory_limit: int | None = None,
    ) -> "SandboxConfig":
        """Build sandbox configuration from explicit values and environment policy."""
        min_timeout_s = _read_env_float("SINGULAR_SANDBOX_MIN_TIMEOUT", MIN_TIMEOUT_S)
        execution_timeout_s = _coerce_timeout(
            timeout
            if timeout is not None
            else _read_env_float(SANDBOX_TIMEOUT_ENV, DEFAULT_TIMEOUT_S),
            min_timeout_s,
        )
        startup_grace_s = _coerce_timeout(
            _read_env_float(SANDBOX_STARTUP_GRACE_ENV, DEFAULT_STARTUP_GRACE_S),
            min_timeout_s,
        )
        configured_memory_limit = (
            memory_limit
            if memory_limit is not None
            else _read_env_int(SANDBOX_MEMORY_LIMIT_ENV, DEFAULT_MEMORY_LIMIT)
        )
        method = os.environ.get(SANDBOX_MP_METHOD_ENV) or None
        return cls(
            execution_timeout_s=execution_timeout_s,
            startup_grace_s=startup_grace_s,
            min_timeout_s=min_timeout_s,
            memory_limit=configured_memory_limit,
            multiprocessing_method=method,
        )


def _read_env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        logger.warning("invalid %s=%r; using %s", name, value, default)
        return default


def _read_env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning("invalid %s=%r; using %s", name, value, default)
        return default


def _coerce_timeout(timeout: float, minimum: float) -> float:
    return max(float(timeout), minimum)


class SandboxError(RuntimeError):
    """Raised when sandboxed code violates a restriction."""


def _validate_ast(tree: ast.AST) -> None:
    """Ensure that the AST does not contain forbidden constructs."""
    for node in ast.walk(tree):
        if isinstance(node, FORBIDDEN_NODES):
            raise SandboxError("forbidden syntax detected")
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            raise SandboxError(f"use of '{node.id}' is forbidden")


def _sandbox_worker(
    code: str,
    execution_timeout_s: float,
    memory_limit: int,
    queue: multiprocessing.Queue[Any],
) -> None:
    """Execute sandboxed code in a child process and return output through *queue*."""
    if resource_module is not None and sys.platform != "win32":
        resource_module.setrlimit(resource_module.RLIMIT_AS, (memory_limit, memory_limit))
        # Keep the OS CPU limit slightly above the user-code timeout so tight
        # loops are reported as sandbox timeouts instead of opaque worker exits.
        cpu_seconds = max(1, int(execution_timeout_s) + 1)
        resource_module.setrlimit(resource_module.RLIMIT_CPU, (cpu_seconds, cpu_seconds))

    tree = ast.parse(code, mode="exec")
    os.environ.clear()
    prev_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            os.chdir(tmpdir)
            queue.put(("started", None))
            allowed = {name: ALLOWED_BUILTINS[name] for name in ALLOWED_BUILTINS}
            env: Dict[str, Any] = {"__builtins__": allowed}
            try:
                exec(compile(tree, "<sandbox>", "exec"), env, env)
                if "result" not in env:
                    queue.put(("error", SandboxError("sandbox code did not set a result")))
                else:
                    queue.put(("result", env["result"]))
            except Exception as exc:  # pragma: no cover - delivered to parent
                queue.put(("error", exc))
        finally:
            try:
                os.chdir(prev_cwd)
            except OSError as exc:  # pragma: no cover - platform specific cleanup guard
                logger.warning("failed to restore cwd during sandbox cleanup: %s", exc)


def _select_multiprocessing_method(configured_method: str | None = None) -> str:
    """Choose the lowest-overhead multiprocessing method available for this host."""
    available = multiprocessing.get_all_start_methods()
    if configured_method:
        if configured_method not in available:
            raise SandboxError(
                f"multiprocessing method {configured_method!r} is unavailable; "
                f"available methods: {', '.join(available)}"
            )
        return configured_method
    if os.name == "posix":
        for method in ("forkserver", "fork", "spawn"):
            if method in available:
                return method
    return "spawn" if "spawn" in available else available[0]


def _read_message(
    queue: multiprocessing.Queue[Any],
    proc: multiprocessing.Process,
    timeout_s: float,
    empty_message: str,
) -> tuple[str, Any]:
    try:
        message = queue.get(timeout=timeout_s)
    except queue_module.Empty as exc:
        if proc.exitcode not in (0, None):
            raise SandboxError(
                f"sandbox worker exited without payload (exit code {proc.exitcode})"
            ) from exc
        raise SandboxError(empty_message) from exc
    if not (isinstance(message, tuple) and len(message) == 2):
        return ("result", message)
    return message


def run(
    code: str,
    timeout: float | None = None,
    memory_limit: int | None = None,
    *,
    config: SandboxConfig | None = None,
) -> Any:
    """Execute *code* in a restricted environment and return the value of `result`.

    A :class:`TimeoutError` is raised if user code exceeds the configured
    execution timeout. Process startup has a separate grace period so normal
    process creation overhead is not charged to user code. Defaults can be
    overridden with ``SINGULAR_SANDBOX_TIMEOUT`` and related sandbox variables.

    On Windows (or platforms without :mod:`resource`), memory/CPU limits are not
    enforced.
    """
    tree = ast.parse(code, mode="exec")
    _validate_ast(tree)

    sandbox_config = config or SandboxConfig.from_environment(
        timeout=timeout,
        memory_limit=memory_limit,
    )
    method = _select_multiprocessing_method(sandbox_config.multiprocessing_method)
    ctx = multiprocessing.get_context(method)
    queue: multiprocessing.Queue[Any] = ctx.Queue()
    proc = ctx.Process(
        target=_sandbox_worker,
        args=(
            code,
            sandbox_config.execution_timeout_s,
            sandbox_config.memory_limit,
            queue,
        ),
    )
    proc.start()

    try:
        status, payload = _read_message(
            queue,
            proc,
            sandbox_config.startup_grace_s,
            "sandbox worker did not start before the startup grace period elapsed",
        )
    except SandboxError as exc:
        if proc.is_alive():
            proc.terminate()
            proc.join()
            raise TimeoutError("sandbox process startup timed out") from exc
        proc.join()
        raise

    if status != "started":
        proc.join()
        if status == "error" and isinstance(payload, Exception):
            raise payload
        return payload

    proc.join(sandbox_config.execution_timeout_s)
    if proc.is_alive():
        proc.terminate()
        proc.join()
        raise TimeoutError("sandbox execution timed out")

    status, payload = _read_message(
        queue,
        proc,
        sandbox_config.min_timeout_s,
        "sandbox worker finished without returning a payload",
    )
    if status == "error" and isinstance(payload, Exception):
        raise payload
    if status != "result":
        raise SandboxError(f"sandbox worker returned unexpected status {status!r}")
    return payload
