from __future__ import annotations

"""Specification loading utilities."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, List
import json


@dataclass
class Example:
    """Single input/output pair."""

    inputs: List[Any]
    output: Any


@dataclass
class Spec:
    """Loaded specification data."""

    name: str
    examples: List[Example]


def load(path: Path) -> Spec:
    """Parse *path* as a JSON spec and return a :class:`Spec`.

    The expected format is::

        {
            "name": "skill_name",
            "examples": [
                {"input": [..], "output": ..},
                ...
            ]
        }

    Each example's ``input`` may be a single value or a list of positional
    arguments.
    """

    data = json.loads(path.read_text(encoding="utf-8"))
    name = data["name"]
    examples: List[Example] = []
    for entry in data.get("examples", []):
        inp = entry.get("input")
        inputs = inp if isinstance(inp, list) else [inp]
        examples.append(Example(inputs=inputs, output=entry.get("output")))
    return Spec(name=name, examples=examples)
