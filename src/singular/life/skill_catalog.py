"""Skill catalog metadata extraction and persistence utilities."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any


_CATALOG_FILENAME = "skill_catalog.json"


_LINE_PATTERN = re.compile(r"^\s*([a-zA-Z_][a-zA-Z0-9_\- ]*)\s*:\s*(.+?)\s*$")


def catalog_path(mem_dir: Path) -> Path:
    """Return the path of the skill catalog file for ``mem_dir``."""

    return Path(mem_dir) / _CATALOG_FILENAME


def refresh_skill_catalog(*, skills_dir: Path, mem_dir: Path) -> dict[str, dict[str, Any]]:
    """Scan ``skills_dir`` and persist a lightweight metadata catalog in ``mem_dir``."""

    catalog: dict[str, dict[str, Any]] = {}
    for skill_file in sorted(Path(skills_dir).glob("*.py")):
        catalog[skill_file.stem] = _extract_skill_metadata(skill_file)

    path = catalog_path(mem_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    return catalog


def read_skill_catalog(mem_dir: Path) -> dict[str, dict[str, Any]]:
    """Read ``mem/skill_catalog.json`` if it exists."""

    path = catalog_path(mem_dir)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, value in payload.items():
        if isinstance(key, str) and isinstance(value, dict):
            out[key] = value
    return out


def _extract_skill_metadata(skill_file: Path) -> dict[str, Any]:
    source = skill_file.read_text(encoding="utf-8")
    parse_errors: list[str] = []
    module = ast.parse(source)

    module_doc = ast.get_docstring(module) or ""
    doc = _parse_docstring_annotations(module_doc, parse_errors)

    run_node = _find_primary_callable(module)
    input_format = doc.get("input_format") or _annotation_to_text(
        run_node.args.args[0].annotation if run_node and run_node.args.args else None
    )
    output_format = doc.get("output_format") or _annotation_to_text(
        run_node.returns if run_node else None
    )

    reliability = _parse_float(doc.get("reliability"), 0.5, parse_errors, "reliability")
    estimated_cost = _parse_float(doc.get("estimated_cost"), 0.5, parse_errors, "estimated_cost")

    capability_tags = _split_csv(doc.get("capability_tags"))
    if not capability_tags:
        capability_tags = _infer_capabilities(skill_file.stem, run_node)

    preconditions = _split_csv(doc.get("preconditions"))

    metadata: dict[str, Any] = {
        "skill": skill_file.stem,
        "capability_tags": capability_tags,
        "preconditions": preconditions,
        "input_format": input_format or "unknown",
        "output_format": output_format or "unknown",
        "estimated_cost": max(0.0, estimated_cost),
        "reliability": min(1.0, max(0.0, reliability)),
        "annotation_valid": len(parse_errors) == 0,
        "parse_errors": parse_errors,
    }
    return metadata


def _find_primary_callable(module: ast.Module) -> ast.FunctionDef | None:
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == "run":
            return node
    for node in module.body:
        if isinstance(node, ast.FunctionDef):
            return node
    return None


def _parse_docstring_annotations(doc: str, parse_errors: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    aliases = {
        "capabilities": "capability_tags",
        "capability tags": "capability_tags",
        "capability_tags": "capability_tags",
        "preconditions": "preconditions",
        "input": "input_format",
        "input_format": "input_format",
        "output": "output_format",
        "output_format": "output_format",
        "cost": "estimated_cost",
        "estimated_cost": "estimated_cost",
        "reliability": "reliability",
    }
    for line in doc.splitlines():
        match = _LINE_PATTERN.match(line)
        if not match:
            continue
        raw_key = match.group(1).strip().lower()
        value = match.group(2).strip()
        key = aliases.get(raw_key)
        if not key:
            continue
        values[key] = value

    if "reliability" in values and _safe_float(values["reliability"]) is None:
        parse_errors.append("invalid reliability")
    if "estimated_cost" in values and _safe_float(values["estimated_cost"]) is None:
        parse_errors.append("invalid estimated_cost")
    return values


def _split_csv(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [piece.strip() for piece in raw.split(",") if piece.strip()]


def _safe_float(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _parse_float(raw: str | None, default: float, parse_errors: list[str], name: str) -> float:
    parsed = _safe_float(raw)
    if parsed is None:
        if raw is not None:
            parse_errors.append(f"{name} must be a float")
        return default
    return parsed


def _annotation_to_text(annotation: ast.expr | None) -> str | None:
    if annotation is None:
        return None
    try:
        return ast.unparse(annotation)
    except Exception:
        return None


def _infer_capabilities(stem: str, run_node: ast.FunctionDef | None) -> list[str]:
    inferred = [piece for piece in stem.split("_") if piece]
    if run_node and run_node.name != "run":
        inferred.append(run_node.name)
    deduped: list[str] = []
    seen: set[str] = set()
    for item in inferred:
        norm = item.lower()
        if norm not in seen:
            deduped.append(norm)
            seen.add(norm)
    return deduped
