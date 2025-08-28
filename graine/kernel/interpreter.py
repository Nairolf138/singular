"""In-process execution of whitelisted patch operations."""

from __future__ import annotations

import os
import signal
import time
from typing import Any, Dict, Callable, Optional, Set

try:  # pragma: no cover - psutil is optional
    import psutil
except Exception:  # pragma: no cover - fallback if psutil missing
    psutil = None  # type: ignore[assignment]


def _current_rss() -> int:
    """Return current resident set size in bytes."""

    if psutil is not None:  # pragma: no cover - simple passthrough
        return psutil.Process().memory_info().rss
    # Fallback to procfs which is available on Linux systems.
    with open("/proc/self/statm", "r", encoding="utf8") as fh:
        pages = int(fh.readline().split()[0])
    return pages * os.sysconf("SC_PAGE_SIZE")


class _LimitManager:
    """Track execution quotas for operations, time and memory."""

    def __init__(self) -> None:
        self.max_ops = 0
        self.mem_limit = 0
        self.ops = 0

    def start(self, op_limit: int, timeout: float, mem_limit: int) -> None:
        self.max_ops = op_limit
        self.mem_limit = mem_limit
        self.ops = 0
        signal.signal(signal.SIGALRM, self._on_timeout)
        signal.setitimer(signal.ITIMER_REAL, timeout)

    def stop(self) -> None:
        signal.setitimer(signal.ITIMER_REAL, 0)

    def _on_timeout(self, *_: Any) -> None:  # pragma: no cover - signal path
        raise RuntimeError("CPU time limit exceeded")

    def tick(self) -> None:
        self.ops += 1
        if self.ops > self.max_ops:
            raise RuntimeError("operation count exceeded")
        if _current_rss() > self.mem_limit:
            raise RuntimeError("RAM limit exceeded")


limits = _LimitManager()


# Simple marker used to tag whitelisted operators as pure.  The execute
# function below will only dispatch to callables carrying this attribute.
def pure(
    func: Callable[[Dict[str, Any]], Optional[bytearray]],
) -> Callable[[Dict[str, Any]], Optional[bytearray]]:
    func.__pure__ = True  # type: ignore[attr-defined]
    return func


@pure
def const_tune(_: Dict[str, Any]) -> None:
    """Adjust a constant; simulated as a no-op."""
    return None


@pure
def eq_rewrite(_: Dict[str, Any]) -> None:
    """Apply an equality rewrite; simulated as a no-op."""
    return None


@pure
def inline(op: Dict[str, Any]) -> Optional[bytearray]:
    """Simulate inlining by optionally allocating memory or sleeping."""

    data: Optional[bytearray] = None
    if size := op.get("size"):
        data = bytearray(int(size))
    if sleep := op.get("sleep"):
        time.sleep(float(sleep))
    return data


@pure
def extract(_: Dict[str, Any]) -> None:
    """Extract code into a new function; simulated as a no-op."""
    return None


@pure
def deadcode_elim(_: Dict[str, Any]) -> None:
    """Eliminate dead code; simulated as a no-op."""
    return None


@pure
def micro_memo(_: Dict[str, Any]) -> None:
    """Introduce micro memoisation; simulated as a no-op."""
    return None


# Map of allowed operation names to their implementation functions.
OPERATIONS: Dict[str, Callable[[Dict[str, Any]], Optional[bytearray]]] = {
    "CONST_TUNE": const_tune,
    "EQ_REWRITE": eq_rewrite,
    "INLINE": inline,
    "EXTRACT": extract,
    "DEADCODE_ELIM": deadcode_elim,
    "MICRO_MEMO": micro_memo,
}

# Public set of allowed operation names for external modules.
ALLOWED_OPS: Set[str] = set(OPERATIONS.keys())


def execute(op: Dict[str, Any]) -> None:
    """Execute a single operation.

    Dispatches to whitelisted operator implementations.  After the operation
    finishes the global :data:`limits` are updated.  Only callables decorated
    with :func:`pure` are allowed to be executed.
    """

    name = op.get("op")
    func = OPERATIONS.get(name)
    if func is None:
        raise RuntimeError(f"Forbidden operation: {name}")
    if not getattr(func, "__pure__", False):  # pragma: no cover - defensive
        raise RuntimeError("operation not marked as pure")

    data = None
    try:
        data = func(op)
        limits.tick()
    finally:
        # Ensure any temporary buffers are released promptly.
        if data is not None:
            del data


__all__ = ["ALLOWED_OPS", "execute", "limits"]
