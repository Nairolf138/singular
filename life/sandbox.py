"""Restricted sandbox execution environment."""

from __future__ import annotations

import ast
import multiprocessing
import os
import resource
import tempfile
from typing import Any, Dict


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


def run(code: str, timeout: float = 1.5, memory_limit: int = 256 * 1024 * 1024) -> Any:
    """Execute *code* in a restricted environment and return the value of `result`.

    A :class:`TimeoutError` is raised if the execution exceeds *timeout* seconds.
    A :class:`MemoryError` is raised if the code exceeds *memory_limit* bytes of
    address space.
    """
    tree = ast.parse(code, mode="exec")
    _validate_ast(tree)

    queue: multiprocessing.Queue[Any] = multiprocessing.Queue()

    def target(q: multiprocessing.Queue[Any]) -> None:
        resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))
        cpu_seconds = max(1, int(timeout))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        os.environ.clear()
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)
            allowed = {name: ALLOWED_BUILTINS[name] for name in ALLOWED_BUILTINS}
            env: Dict[str, Any] = {"__builtins__": allowed}
            try:
                exec(compile(tree, "<sandbox>", "exec"), env, env)
                q.put(env.get("result"))
            except Exception as exc:  # pragma: no cover - delivered to parent
                q.put(exc)

    proc = multiprocessing.Process(target=target, args=(queue,))
    proc.start()
    proc.join(timeout)
    if proc.is_alive():
        proc.terminate()
        proc.join()
        raise TimeoutError("sandbox execution timed out")

    if not queue.empty():
        out = queue.get()
        if isinstance(out, Exception):
            raise out
        return out
    return None
