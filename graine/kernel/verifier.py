"""Patch verifier for the Graine kernel."""

from __future__ import annotations

from typing import Any, Dict, List

import yaml

from .interpreter import ALLOWED_OPS

class VerificationError(Exception):
    """Raised when a patch fails verification."""


def load_zones(path: str = "configs/zones.yaml") -> Dict[str, Any]:
    with open(f"graine/{path}", "r", encoding="utf8") as fh:
        return yaml.safe_load(fh)


def verify_patch(patch: Dict[str, Any]) -> None:
    """Verify a patch dictionary against basic rules.

    This function implements only a subset of the full specification.
    """
    if patch.get("type") != "Patch":
        raise VerificationError("type must be 'Patch'")

    target = patch.get("target")
    if not target or "file" not in target or "function" not in target:
        raise VerificationError("target must specify file and function")

    zones = load_zones()["targets"]
    if not any(z["file"] == target["file"] and z["function"] == target["function"] for z in zones):
        raise VerificationError("target not whitelisted")

    ops: List[Dict[str, Any]] = patch.get("ops", [])
    if not isinstance(ops, list) or not ops:
        raise VerificationError("ops must be a non-empty list")

    for op in ops:
        name = op.get("op")
        if name not in ALLOWED_OPS:
            raise VerificationError(f"operator {name} not allowed")
        if name == "CONST_TUNE":
            delta = op.get("delta")
            bounds = op.get("bounds")
            if delta is None or bounds is None:
                raise VerificationError("CONST_TUNE requires delta and bounds")
            if not (bounds[0] <= delta <= bounds[1]):
                raise VerificationError("delta outside bounds")

    limits = patch.get("limits", {})
    diff_max = limits.get("diff_max", 0)
    if diff_max > 12:
        raise VerificationError("diff_max exceeds limit of 12")
