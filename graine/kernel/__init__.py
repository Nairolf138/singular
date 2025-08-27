"""Kernel for patch verification and execution.

This is a minimal placeholder implementation focusing on schema validation.
"""
from .verifier import VerificationError, verify_patch

ALLOWED_OPS = {
    "CONST_TUNE",
    "EQ_REWRITE",
    "INLINE",
    "EXTRACT",
    "DEADCODE_ELIM",
    "MICRO_MEMO",
}


def run_variant(patch):
    """Validate and execute a patch variant.

    Currently only performs validation and returns a dummy result.
    """
    verify_patch(patch)
    return {"status": "validated"}

__all__ = ["run_variant", "verify_patch", "VerificationError"]
