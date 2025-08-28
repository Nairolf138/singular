"""Specification loading utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, List
import json


class SpecValidationError(ValueError):
    """Raised when a specification fails validation."""


@dataclass
class Example:
    """Single input/output pair."""

    inputs: List[Any]
    output: Any


@dataclass
class Constraints:
    """Execution constraints for a generated skill."""

    pure: bool
    no_import: bool
    time_ms_max: int


@dataclass
class Spec:
    """Loaded specification data."""

    name: str
    signature: str
    examples: List[Example]
    constraints: Constraints


def load(path: Path) -> Spec:
    """Parse *path* as a JSON spec and return a :class:`Spec`.

    The expected format is::

        {
            "name": "skill_name",
            "signature": "skill(arg1, arg2)",
            "examples": [
                {"input": [..], "output": ..},
                ...,
            ],
            "constraints": {
                "pure": true,
                "no_import": true,
                "time_ms_max": 1000
            }
        }

    Each example's ``input`` may be a single value or a list of positional
    arguments.  The ``constraints`` object is mandatory and must request pure
    operation, disallow imports and specify a positive ``time_ms_max`` value.
    """

    data = json.loads(path.read_text(encoding="utf-8"))

    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise SpecValidationError("'name' must be a non-empty string")

    signature = data.get("signature")
    if not isinstance(signature, str) or not signature.strip():
        raise SpecValidationError("'signature' must be a non-empty string")

    examples_raw = data.get("examples")
    if not isinstance(examples_raw, list) or not examples_raw:
        raise SpecValidationError("'examples' must be a non-empty list")

    examples: List[Example] = []
    for idx, entry in enumerate(examples_raw):
        if not isinstance(entry, dict):
            raise SpecValidationError(f"example {idx} must be an object")
        if "input" not in entry:
            raise SpecValidationError(f"example {idx} missing 'input'")
        if "output" not in entry:
            raise SpecValidationError(f"example {idx} missing 'output'")
        inp = entry.get("input")
        inputs = inp if isinstance(inp, list) else [inp]
        examples.append(Example(inputs=inputs, output=entry.get("output")))

    constraints_raw = data.get("constraints")
    if not isinstance(constraints_raw, dict):
        raise SpecValidationError("'constraints' must be an object")

    pure = constraints_raw.get("pure")
    if pure is not True:
        raise SpecValidationError("'constraints.pure' must be true")

    no_import = constraints_raw.get("no_import")
    if no_import is not True:
        raise SpecValidationError("'constraints.no_import' must be true")

    time_ms_max = constraints_raw.get("time_ms_max")
    if not isinstance(time_ms_max, int) or time_ms_max <= 0:
        raise SpecValidationError("'constraints.time_ms_max' must be a positive integer")

    constraints = Constraints(pure=True, no_import=True, time_ms_max=time_ms_max)

    return Spec(name=name, signature=signature, examples=examples, constraints=constraints)
