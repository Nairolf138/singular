"""Generate candidate patches based on configuration zones.

This module reads the ``zones.yaml`` configuration and produces minimal
``Patch`` objects that respect the allowed operators and other constraints
specified for each zone. The parsing logic mirrors the lightweight approach
used elsewhere in the project to avoid external dependencies.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .dsl import (
    Patch,
    CYCLOMATIC_LIMIT,
    THETA_DIFF_LIMIT,
    DSLValidationError,
)


def load_zones(path: Path | None = None) -> List[Dict[str, Any]]:
    """Parse ``zones.yaml`` without external YAML parsers.

    Parameters
    ----------
    path:
        Optional path to the configuration file. When omitted, the default
        project configuration is used.

    Returns
    -------
    list of dict
        Each dict represents a mutation zone with keys ``file``, ``function``,
        ``purity``, ``max_cyclomatic`` and ``operators``.
    """

    if path is None:
        path = Path(__file__).resolve().parents[1] / "configs" / "zones.yaml"

    zones: List[Dict[str, Any]] = []
    current: Dict[str, Any] | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        if raw.startswith("targets:"):
            continue
        if raw.startswith("  -"):
            if current:
                zones.append(current)
            current = {}
            continue
        if current is None:
            continue
        line = raw.strip()
        if line.startswith("file:"):
            current["file"] = line.split(":", 1)[1].strip()
        elif line.startswith("function:"):
            current["function"] = line.split(":", 1)[1].strip()
        elif line.startswith("purity:"):
            current["purity"] = line.split(":", 1)[1].strip().lower() == "true"
        elif line.startswith("max_cyclomatic:"):
            current["max_cyclomatic"] = int(line.split(":", 1)[1].strip())
        elif line == "operators:":
            current["operators"] = []
        elif line.startswith("-") and "operators" in current:
            op = line.split("-", 1)[1].strip()
            current["operators"].append(op)
    if current:
        zones.append(current)
    return zones


def propose_mutations(zones: List[Dict[str, Any]] | None = None) -> List[Patch]:
    """Return valid ``Patch`` objects for all configured operators.

    Each zone in ``zones.yaml`` may list multiple operators.  A patch is
    produced for every operator while ensuring that global constraints such as
    ``THETA_DIFF_LIMIT`` and ``CYCLOMATIC_LIMIT`` are honoured.  Invalid patches
    are filtered out by running ``validate`` on each candidate.
    """

    if zones is None:
        zones = load_zones()

    patches: List[Patch] = []
    for zone in zones:
        ops = zone.get("operators", [])
        for op_name in ops:
            try:
                patch = Patch.from_dict(
                    {
                        "target": {
                            "file": zone.get("file", ""),
                            "function": zone.get("function", ""),
                        },
                        "ops": [{"op": op_name}],
                        "theta_diff": min(
                            zone.get("theta_diff", 0.0), THETA_DIFF_LIMIT
                        ),
                        "purity": zone.get("purity", True),
                        "cyclomatic": min(
                            zone.get("max_cyclomatic", 0), CYCLOMATIC_LIMIT
                        ),
                    }
                )
                if patch.validate():
                    patches.append(patch)
            except (DSLValidationError, ValueError):
                # Skip invalid operators or patches that fail validation
                continue
    return patches
