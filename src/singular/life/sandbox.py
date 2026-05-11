"""Restricted sandbox execution environment."""

from __future__ import annotations

import ast
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
    timeout: float,
    memory_limit: int,
    queue: multiprocessing.Queue[Any],
) -> None:
    """Execute sandboxed code in a child process and return output through *queue*."""
    if resource_module is not None and sys.platform != "win32":
        resource_module.setrlimit(resource_module.RLIMIT_AS, (memory_limit, memory_limit))
        cpu_seconds = max(1, int(timeout))
        resource_module.setrlimit(resource_module.RLIMIT_CPU, (cpu_seconds, cpu_seconds))

    tree = ast.parse(code, mode="exec")
    os.environ.clear()
    prev_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            os.chdir(tmpdir)
            allowed = {name: ALLOWED_BUILTINS[name] for name in ALLOWED_BUILTINS}
            env: Dict[str, Any] = {"__builtins__": allowed}
            try:
                exec(compile(tree, "<sandbox>", "exec"), env, env)
                if "result" not in env:
                    queue.put(SandboxError("sandbox code did not set a result"))
                else:
                    queue.put(env["result"])
            except Exception as exc:  # pragma: no cover - delivered to parent
                queue.put(exc)
        finally:
            try:
                os.chdir(prev_cwd)
            except OSError as exc:  # pragma: no cover - platform specific cleanup guard
                logger.warning("failed to restore cwd during sandbox cleanup: %s", exc)


def run(code: str, timeout: float = 1.5, memory_limit: int = 256 * 1024 * 1024) -> Any:
    """Execute *code* in a restricted environment and return the value of `result`.

    A :class:`TimeoutError` is raised if the execution exceeds *timeout* seconds.
    A :class:`MemoryError` is raised if the code exceeds *memory_limit* bytes of
    address space.

    On Windows (or platforms without :mod:`resource`), memory/CPU limits are not
    enforced.
    """
    tree = ast.parse(code, mode="exec")
    _validate_ast(tree)

    ctx = multiprocessing.get_context("spawn")
    queue: multiprocessing.Queue[Any] = ctx.Queue()
    proc = ctx.Process(target=_sandbox_worker, args=(code, timeout, memory_limit, queue))
    proc.start()
    proc.join(timeout)
    if proc.is_alive():
        proc.terminate()
        proc.join()
        raise TimeoutError("sandbox execution timed out")
    queue_timeout = max(0.05, timeout)
    try:
        out = queue.get(timeout=queue_timeout)
    except queue_module.Empty as exc:
        if proc.exitcode not in (0, None):
            raise SandboxError(
                f"sandbox worker exited without payload (exit code {proc.exitcode})"
            ) from exc
        raise SandboxError(
            "sandbox worker finished without returning a payload"
        ) from exc

    if isinstance(out, Exception):
        raise out
    return out
