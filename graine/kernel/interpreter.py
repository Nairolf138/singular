"""In-process execution of whitelisted patch operations."""
from __future__ import annotations

import os
import signal
import time
from typing import Any, Dict, Set

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

# Whitelisted operations understood by the interpreter.
ALLOWED_OPS: Set[str] = {
    "CONST_TUNE",
    "EQ_REWRITE",
    "INLINE",
    "EXTRACT",
    "DEADCODE_ELIM",
    "MICRO_MEMO",
}


def execute(op: Dict[str, Any]) -> None:
    """Execute a single operation.

    The interpreter validates the operation name and applies a few helper
    behaviours used in tests such as sleeping or allocating memory.  After
    each operation the global :data:`limits` are updated.
    """
    name = op.get("op")
    if name not in ALLOWED_OPS:
        raise RuntimeError(f"Forbidden operation: {name}")
    data = None
    try:
        if name == "INLINE":
            if (size := op.get("size")):
                data = bytearray(int(size))
            if (sleep := op.get("sleep")):
                time.sleep(float(sleep))
        limits.tick()
    finally:
        # Ensure any temporary buffers are released promptly.
        if data is not None:
            del data


__all__ = ["ALLOWED_OPS", "execute", "limits"]
