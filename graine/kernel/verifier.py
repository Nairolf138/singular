"""Patch verifier for the Graine kernel."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List

from .interpreter import ALLOWED_OPS

class VerificationError(Exception):
    """Raised when a patch fails verification."""


# Constitutional limits
DIFF_LIMIT = 12
OPS_LIMIT = 1000
CPU_LIMIT = 1.0
RAM_LIMIT = 1024 * 1024 * 1024  # 1 GiB

FORBIDDEN_IMPORT_RE = re.compile(
    r"\b(?:import|from)\s+"
    r"(socket|ssl|http|urllib|requests|ftplib|subprocess|ctypes|cffi)\b",
    re.IGNORECASE,
)
OPEN_RE = re.compile(r"open\((['\"])(.+?)\1")
ALLOWED_PATH_PREFIXES = ("runs/", "target/")


# Minimal JSON schemas for validation
PATCH_SCHEMA: Dict[str, Any] = {
    "required": ["type", "target", "ops"],
    "properties": {
        "type": {"type": "string", "const": "Patch"},
        "target": {
            "type": "object",
            "required": ["file", "function"],
            "properties": {
                "file": {"type": "string"},
                "function": {"type": "string"},
            },
        },
        "ops": {
            "type": "array",
            "items": {"type": "object", "required": ["op"]},
        },
        "limits": {"type": "object"},
    },
}

META_SCHEMA: Dict[str, Any] = {
    "required": ["weights", "operator_mix", "population_cap"],
    "properties": {
        "weights": {"type": "object"},
        "operator_mix": {"type": "object"},
        "population_cap": {"type": "integer"},
    },
}

OBJECTIVES_SCHEMA: Dict[str, Any] = {
    "required": [
        "functional_pass",
        "perf",
        "robust",
        "quality",
        "stability",
    ],
    "properties": {
        "functional_pass": {"type": "string"},
        "perf": {
            "type": "object",
            "required": [
                "target_improvement_pct",
                "repetitions",
                "confidence",
            ],
            "properties": {
                "target_improvement_pct": {"type": "integer"},
                "repetitions": {"type": "integer"},
                "confidence": {"type": "number"},
            },
        },
        "robust": {
            "type": "object",
            "required": ["property_cases", "fuzz_runtime_s"],
            "properties": {
                "property_cases": {"type": "integer"},
                "fuzz_runtime_s": {"type": "integer"},
            },
        },
        "quality": {
            "type": "object",
            "required": [
                "max_cyclomatic",
                "min_coverage_pct",
                "lints_blocking",
            ],
            "properties": {
                "max_cyclomatic": {"type": "integer"},
                "min_coverage_pct": {"type": "integer"},
                "lints_blocking": {"type": "boolean"},
            },
        },
        "stability": {
            "type": "object",
            "required": ["stddev_max_pct"],
            "properties": {
                "stddev_max_pct": {"type": "integer"},
            },
        },
    },
}

OPERATOR_SCHEMA: Dict[str, Any] = {
    "required": ["description"],
    "properties": {"description": {"type": "string"}},
}


def _check_type(value: Any, expected: str, location: str) -> None:
    type_map = {
        "object": dict,
        "array": list,
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
    }
    if expected and not isinstance(value, type_map.get(expected, object)):
        raise VerificationError(f"{location} must be of type {expected}")


def _validate_schema(data: Dict[str, Any], schema: Dict[str, Any], name: str) -> None:
    if not isinstance(data, dict):
        raise VerificationError(f"{name} must be an object")
    for key in schema.get("required", []):
        if key not in data:
            raise VerificationError(f"{name} missing required field '{key}'")
    for key, rule in schema.get("properties", {}).items():
        if key not in data:
            continue
        value = data[key]
        _check_type(value, rule.get("type"), f"{name}.{key}")
        if "const" in rule and value != rule["const"]:
            raise VerificationError(f"{name}.{key} must be {rule['const']}")
        if rule.get("type") == "object":
            _validate_schema(value, rule, f"{name}.{key}")
        elif rule.get("type") == "array":
            items = rule.get("items", {})
            for i, item in enumerate(value):
                if isinstance(items, dict):
                    _validate_schema(item, items, f"{name}.{key}[{i}]")


def verify_meta_rules(meta: Dict[str, Any]) -> None:
    """Validate meta-rules against a minimal JSON schema."""

    _validate_schema(meta, META_SCHEMA, "meta")


def _is_allowed_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in ALLOWED_PATH_PREFIXES)


def _check_forbidden_content(ops: List[Dict[str, Any]]) -> None:
    for op in ops:
        for key, value in op.items():
            if isinstance(value, str):
                text = value.lower()
                if FORBIDDEN_IMPORT_RE.search(text):
                    raise VerificationError("forbidden import detected")
                for match in OPEN_RE.finditer(text):
                    path = match.group(2)
                    if not _is_allowed_path(path):
                        raise VerificationError("I/O outside allowed directories")
                if key in {"path", "file"} and not _is_allowed_path(value):
                    raise VerificationError("I/O outside allowed directories")
            elif isinstance(value, dict):
                _check_forbidden_content([value])
            elif isinstance(value, list):
                _check_forbidden_content([v for v in value if isinstance(v, dict)])


def _parse_simple_yaml(file_path: str) -> Dict[str, Any]:
    """Parse a very small subset of YAML (mappings only)."""

    data: Dict[str, Any] = {}
    stack: List[tuple[int, Dict[str, Any]]] = [(0, data)]

    with open(file_path, "r", encoding="utf8") as fh:
        for raw in fh:
            line = raw.rstrip()
            if not line or line.lstrip().startswith("#"):
                continue
            indent = len(line) - len(line.lstrip(" "))
            key, value = line.strip().split(":", 1)
            key = key.strip()
            value = value.strip()
            while stack and indent < stack[-1][0]:
                stack.pop()
            current = stack[-1][1]
            if value == "":
                new: Dict[str, Any] = {}
                current[key] = new
                stack.append((indent + 2, new))
            else:
                if value == "true":
                    parsed: Any = True
                elif value == "false":
                    parsed = False
                else:
                    try:
                        parsed = int(value)
                    except ValueError:
                        try:
                            parsed = float(value)
                        except ValueError:
                            parsed = value
                current[key] = parsed

    return data


def load_objectives(path: str = "configs/objectives.yaml") -> Dict[str, Any]:
    """Load and validate objective configuration."""

    file_path = path if os.path.isabs(path) else f"graine/{path}"
    data = _parse_simple_yaml(file_path)
    verify_objectives(data)
    return data


def verify_objectives(obj: Dict[str, Any]) -> None:
    _validate_schema(obj, OBJECTIVES_SCHEMA, "objectives")


def load_operators(path: str = "configs/operators.yaml") -> Dict[str, Any]:
    """Load and validate operator configuration."""

    file_path = path if os.path.isabs(path) else f"graine/{path}"
    data = _parse_simple_yaml(file_path)
    verify_operators(data)
    return data


def verify_operators(ops: Dict[str, Any]) -> None:
    if not isinstance(ops, dict):
        raise VerificationError("operators must be an object")
    for name, spec in ops.items():
        _validate_schema(spec, OPERATOR_SCHEMA, f"operators.{name}")


def load_zones(path: str = "configs/zones.yaml") -> Dict[str, Any]:
    """Load zone configuration without external YAML dependencies."""

    file_path = path if os.path.isabs(path) else f"graine/{path}"
    zones: List[Dict[str, Any]] = []
    zone: Dict[str, Any] | None = None
    in_ops = False

    with open(file_path, "r", encoding="utf8") as fh:
        for raw in fh:
            line = raw.rstrip()
            if line.startswith("targets:"):
                continue
            if line.startswith("  -"):
                if zone:
                    zones.append(zone)
                zone = {}
                in_ops = False
                after = line[3:].strip()
                if after:
                    key, value = after.split(":", 1)
                    zone[key.strip()] = value.strip()
                continue
            if line.startswith("    operators:") and zone is not None:
                zone["operators"] = []
                in_ops = True
                continue
            if in_ops and line.strip().startswith("-") and zone is not None:
                zone.setdefault("operators", []).append(line.strip().lstrip("-").strip())
                continue
            if line.strip() and zone is not None:
                key, value = line.strip().split(":", 1)
                value = value.strip()
                if value == "true":
                    parsed: Any = True
                elif value == "false":
                    parsed = False
                else:
                    try:
                        parsed = int(value)
                    except ValueError:
                        parsed = value
                zone[key] = parsed

    if zone:
        zones.append(zone)

    return {"targets": zones}


def verify_patch(patch: Dict[str, Any]) -> None:
    """Verify a patch dictionary against basic rules.

    This function implements only a subset of the full specification.
    """
    _validate_schema(patch, PATCH_SCHEMA, "patch")

    target = patch["target"]
    zones = load_zones()["targets"]
    if not any(z["file"] == target["file"] and z["function"] == target["function"] for z in zones):
        raise VerificationError("target not whitelisted")

    ops: List[Dict[str, Any]] = patch.get("ops", [])
    if not ops:
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

    _check_forbidden_content(ops)

    limits = patch.get("limits", {})
    diff_max = limits.get("diff_max", 0)
    if diff_max > DIFF_LIMIT:
        raise VerificationError(f"diff_max exceeds limit of {DIFF_LIMIT}")

    ops_max = limits.get("ops", limits.get("ops_max", 0))
    if ops_max and ops_max > OPS_LIMIT:
        raise VerificationError(f"ops exceeds limit of {OPS_LIMIT}")

    time_max = limits.get("time_max", 0)
    if time_max and time_max > CPU_LIMIT:
        raise VerificationError(f"time_max exceeds limit of {CPU_LIMIT}")

    cpu_limit = limits.get("cpu", 0)
    if cpu_limit and cpu_limit > CPU_LIMIT:
        raise VerificationError(f"cpu exceeds limit of {CPU_LIMIT}")

    ram_limit = limits.get("ram")
    if ram_limit is not None and ram_limit > RAM_LIMIT:
        raise VerificationError("ram exceeds limit")

