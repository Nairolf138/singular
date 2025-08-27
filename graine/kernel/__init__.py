"""Kernel for patch verification and execution."""
from __future__ import annotations

import time
import resource
from typing import Dict, Any

from .interpreter import ALLOWED_OPS, execute
from .logger import JsonlLogger
from .verifier import VerificationError, verify_patch


DEFAULT_LIMITS = {"cpu": 1.0, "ram": None, "ops": 1000}


def run_variant(patch: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and execute a patch variant.

    Executes whitelisted operations while enforcing simple quotas for CPU
    time, memory usage and operation count.  A hash chained JSONL log is
    written for each invocation.
    """
    verify_patch(patch)
    limits = {**DEFAULT_LIMITS, **patch.get("limits", {})}
    op_limit = limits["ops"]
    cpu_limit = limits["cpu"]
    ram_limit = limits["ram"]

    logger = JsonlLogger()
    ops = patch.get("ops", [])
    start = time.time()
    executed = 0
    logger.log({"event": "start", "ops": len(ops)})
    for op in ops:
        if executed >= op_limit:
            logger.log({"event": "error", "type": "op_limit"})
            raise RuntimeError("operation count exceeded")
        execute(op)
        executed += 1
        elapsed = time.time() - start
        if elapsed > cpu_limit:
            logger.log({"event": "error", "type": "cpu_limit", "elapsed": elapsed})
            raise RuntimeError("CPU time limit exceeded")
        if ram_limit is not None:
            usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
            if usage > ram_limit:
                logger.log({"event": "error", "type": "ram_limit", "ram": usage})
                raise RuntimeError("RAM limit exceeded")
    elapsed = time.time() - start
    logger.log({"event": "success", "ops": executed, "elapsed": elapsed})
    return {"status": "validated", "ops_executed": executed}


__all__ = ["run_variant", "verify_patch", "VerificationError", "ALLOWED_OPS"]
