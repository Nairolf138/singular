"""Kernel for patch verification and execution."""
from __future__ import annotations

import time
from typing import Dict, Any

from .interpreter import ALLOWED_OPS, execute, limits
from .logger import JsonlLogger
from .verifier import VerificationError, verify_patch

DEFAULT_LIMITS = {"cpu": 1.0, "ram": 256 * 1024 * 1024, "ops": 1000}


def run_variant(patch: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and execute a patch variant.

    Executes whitelisted operations while enforcing simple quotas for CPU
    time, memory usage and operation count.  A hash chained JSONL log is
    written for each invocation.
    """
    verify_patch(patch)
    quota = {**DEFAULT_LIMITS, **patch.get("limits", {})}
    op_limit = quota["ops"]
    cpu_limit = quota["cpu"]
    ram_limit = quota["ram"]

    if cpu_limit <= 0:
        raise RuntimeError("CPU time limit exceeded")

    logger = JsonlLogger()
    ops = patch.get("ops", [])
    start = time.time()
    executed = 0
    logger.log({"event": "start", "ops": len(ops)})
    limits.start(op_limit, cpu_limit, ram_limit)
    try:
        for op in ops:
            execute(op)
            executed += 1
    except RuntimeError as err:
        logger.log({"event": "error", "type": str(err)})
        raise
    finally:
        limits.stop()
    elapsed = time.time() - start
    logger.log({"event": "success", "ops": executed, "elapsed": elapsed})
    return {"status": "validated", "ops_executed": executed}


__all__ = ["run_variant", "verify_patch", "VerificationError", "ALLOWED_OPS"]
