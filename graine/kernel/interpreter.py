"""In-process execution of whitelisted patch operations."""
from __future__ import annotations

from typing import Any, Dict, Set

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

    The current implementation is a stub that simply validates the
    operation name.  Real kernels would modify a program representation.
    """
    name = op.get("op")
    if name not in ALLOWED_OPS:
        raise RuntimeError(f"Forbidden operation: {name}")
    # Placeholder for operation-specific behavior.  For now we perform no
    # additional work beyond the whitelist check.
    return None


__all__ = ["ALLOWED_OPS", "execute"]
