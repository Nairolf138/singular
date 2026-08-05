"""Specification loading utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List
import json


class SpecValidationError(ValueError):
    """Raised when a specification fails validation."""


MINIMAL_SPEC_EXAMPLE: dict[str, Any] = {
    "name": "add_two",
    "signature": "add_two(x)",
    "examples": [{"input": [1], "output": 3}],
    "constraints": {"pure": True, "no_import": True, "time_ms_max": 50},
}

FULL_SPEC_EXAMPLE: dict[str, Any] = {
    "name": "repair_loop",
    "signature": "repair_loop(x)",
    "examples": [
        {"input": [1], "output": 1},
        {"input": [2], "output": 2},
    ],
    "constraints": {"pure": True, "no_import": True, "time_ms_max": 50},
    "triggers": [{"signal": "noise", "gte": 0.5}],
    "reward": {"mood": "pleasure", "resource_delta": {"food": 2}},
    "penalty": {"mood": "pain", "resource_delta": {"energy": -1}},
    "cooldown": 60,
    "success": {"resource_min": {"energy": 80}},
    "origin": "intrinsic",
}

QUEST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["name", "signature", "examples", "constraints"],
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "signature": {"type": "string", "minLength": 1},
        "examples": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["input", "output"],
                "properties": {"input": {}, "output": {}},
            },
        },
        "constraints": {
            "type": "object",
            "required": ["pure", "no_import", "time_ms_max"],
            "properties": {
                "pure": {"const": True},
                "no_import": {"const": True},
                "time_ms_max": {"type": "integer", "minimum": 1},
            },
        },
        "triggers": {"type": "array", "items": {"type": "object"}},
        "reward": {"type": "object"},
        "penalty": {"type": "object"},
        "cooldown": {"type": "integer", "minimum": 0},
        "success": {"type": "object"},
        "origin": {"enum": ["intrinsic", "external"]},
    },
    "additionalProperties": True,
}


def _validation_error(field: str, expected: str, example: Any) -> SpecValidationError:
    return SpecValidationError(
        f"Invalid quest spec field {field!r}: expected {expected}. "
        f"Minimal example: {json.dumps(example, ensure_ascii=False, sort_keys=True)}"
    )


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
    triggers: list[dict[str, Any]] = field(default_factory=list)
    reward: dict[str, Any] = field(default_factory=dict)
    penalty: dict[str, Any] = field(default_factory=dict)
    cooldown: int = 0
    success: dict[str, Any] = field(default_factory=dict)
    origin: str = "external"


def load(path: Path) -> Spec:
    """Parse *path* as a JSON spec and return a :class:`Spec`."""

    data = json.loads(path.read_text(encoding="utf-8"))

    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise _validation_error(
            "name", "a non-empty string", {"name": MINIMAL_SPEC_EXAMPLE["name"]}
        )

    signature = data.get("signature")
    if not isinstance(signature, str) or not signature.strip():
        raise _validation_error(
            "signature",
            "a non-empty string such as function_name(arg)",
            {"signature": MINIMAL_SPEC_EXAMPLE["signature"]},
        )

    examples_raw = data.get("examples")
    if not isinstance(examples_raw, list) or not examples_raw:
        raise _validation_error(
            "examples",
            "a non-empty list of input/output objects",
            {"examples": MINIMAL_SPEC_EXAMPLE["examples"]},
        )

    examples: List[Example] = []
    for idx, entry in enumerate(examples_raw):
        if not isinstance(entry, dict):
            raise _validation_error(
                f"examples[{idx}]",
                "an object with input and output",
                {"input": [1], "output": 3},
            )
        if "input" not in entry:
            raise _validation_error(
                f"examples[{idx}].input",
                "a value or list of function arguments",
                {"input": [1]},
            )
        if "output" not in entry:
            raise _validation_error(
                f"examples[{idx}].output", "the expected return value", {"output": 3}
            )
        inp = entry.get("input")
        inputs = inp if isinstance(inp, list) else [inp]
        examples.append(Example(inputs=inputs, output=entry.get("output")))

    constraints_raw = data.get("constraints")
    if not isinstance(constraints_raw, dict):
        raise _validation_error(
            "constraints",
            "an object declaring pure, no_import, and time_ms_max",
            {"constraints": MINIMAL_SPEC_EXAMPLE["constraints"]},
        )

    pure = constraints_raw.get("pure")
    if pure is not True:
        raise _validation_error(
            "constraints.pure", "true", {"constraints": {"pure": True}}
        )

    no_import = constraints_raw.get("no_import")
    if no_import is not True:
        raise _validation_error(
            "constraints.no_import", "true", {"constraints": {"no_import": True}}
        )

    time_ms_max = constraints_raw.get("time_ms_max")
    if not isinstance(time_ms_max, int) or time_ms_max <= 0:
        raise _validation_error(
            "constraints.time_ms_max",
            "a positive integer number of milliseconds",
            {"constraints": {"time_ms_max": 50}},
        )

    triggers = data.get("triggers", [])
    if not isinstance(triggers, list):
        raise _validation_error(
            "triggers",
            "a list of trigger objects",
            {"triggers": FULL_SPEC_EXAMPLE["triggers"]},
        )
    for idx, trigger in enumerate(triggers):
        if not isinstance(trigger, dict):
            raise _validation_error(
                f"triggers[{idx}]", "an object", {"signal": "noise", "gte": 0.5}
            )

    reward = data.get("reward", {})
    if not isinstance(reward, dict):
        raise _validation_error(
            "reward", "an object", {"reward": FULL_SPEC_EXAMPLE["reward"]}
        )

    penalty = data.get("penalty", {})
    if not isinstance(penalty, dict):
        raise _validation_error(
            "penalty", "an object", {"penalty": FULL_SPEC_EXAMPLE["penalty"]}
        )

    cooldown = data.get("cooldown", 0)
    if not isinstance(cooldown, int) or cooldown < 0:
        raise _validation_error("cooldown", "a non-negative integer", {"cooldown": 0})

    success = data.get("success", {})
    if not isinstance(success, dict):
        raise _validation_error(
            "success", "an object", {"success": FULL_SPEC_EXAMPLE["success"]}
        )

    origin = data.get("origin", "external")
    if origin not in {"intrinsic", "external"}:
        raise _validation_error(
            "origin", "'intrinsic' or 'external'", {"origin": "external"}
        )

    constraints = Constraints(pure=True, no_import=True, time_ms_max=time_ms_max)

    return Spec(
        name=name,
        signature=signature,
        examples=examples,
        constraints=constraints,
        triggers=triggers,
        reward=reward,
        penalty=penalty,
        cooldown=cooldown,
        success=success,
        origin=origin,
    )
