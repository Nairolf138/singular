"""Simulation world state backed by ``mem/world_state.json``.

The module is intentionally data-driven: callers can pass generic action
payloads to evolve the world without changing Python code.
"""

from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

_BASE_DIR = Path(os.environ.get("SINGULAR_HOME", "."))
DEFAULT_WORLD_STATE_PATH = _BASE_DIR / "mem" / "world_state.json"


def default_world_state() -> dict[str, Any]:
    """Return the default world model."""

    return {
        "world_clock": 0,
        "map": {
            "spaces": [
                {"id": "core", "kind": "hub", "stability": 0.9},
                {"id": "wilds", "kind": "exploration", "stability": 0.7},
            ],
            "niches": [
                {"id": "craft", "space_id": "core", "specialization": "fabrication"},
                {"id": "research", "space_id": "core", "specialization": "insight"},
                {"id": "forage", "space_id": "wilds", "specialization": "biomass"},
            ],
        },
        "resources": {
            "renewable": {
                "solar": {"amount": 70.0, "regen_rate": 5.0, "capacity": 100.0},
                "biomass": {"amount": 45.0, "regen_rate": 3.0, "capacity": 75.0},
            },
            "non_renewable": {
                "ore": {"amount": 80.0},
                "rare_earth": {"amount": 20.0},
            },
        },
        "external": {
            "entities": [
                {"id": "trader-01", "type": "merchant", "stance": "neutral"},
                {"id": "observer-01", "type": "monitor", "stance": "supportive"},
            ],
            "artifacts": [
                {"id": "relay", "kind": "communication", "integrity": 0.95}
            ],
        },
        "global_health": {
            "score": 82.0,
            "trend": "stable",
            "signals": {
                "resource_pressure": 0.2,
                "cohesion": 0.85,
            },
        },
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    )
    try:
        with tmp:
            json.dump(payload, tmp, ensure_ascii=False, indent=2)
            tmp.write("\n")
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp.name, path)
    finally:
        try:
            os.unlink(tmp.name)
        except FileNotFoundError:
            pass


def load_world_state(path: Path | str | None = None) -> dict[str, Any]:
    """Load world state from disk, creating defaults if absent."""

    world_path = Path(path) if path is not None else DEFAULT_WORLD_STATE_PATH
    if not world_path.exists():
        state = default_world_state()
        _atomic_write_json(world_path, state)
        return state
    with world_path.open(encoding="utf-8") as f:
        return json.load(f)


def save_world_state(state: dict[str, Any], path: Path | str | None = None) -> None:
    """Persist world state to disk."""

    world_path = Path(path) if path is not None else DEFAULT_WORLD_STATE_PATH
    _atomic_write_json(world_path, state)


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def apply_action(
    action: dict[str, Any],
    *,
    state: dict[str, Any] | None = None,
    state_path: Path | str | None = None,
) -> dict[str, Any]:
    """Apply a generic action payload to the world and persist it.

    Supported keys include ``consume_resources``, ``produce_resources``,
    ``health_delta``, ``entities`` and ``artifacts`` (with ``add``/``remove``),
    and ``map_updates`` for adding spaces/niches.
    """

    next_state = deepcopy(state) if state is not None else load_world_state(state_path)

    resources = next_state.setdefault("resources", {})
    renewable = resources.setdefault("renewable", {})
    non_renewable = resources.setdefault("non_renewable", {})

    for name, amount in action.get("consume_resources", {}).get("renewable", {}).items():
        if name not in renewable:
            continue
        renewable[name]["amount"] = max(0.0, renewable[name]["amount"] - max(float(amount), 0.0))

    for name, amount in action.get("consume_resources", {}).get("non_renewable", {}).items():
        if name not in non_renewable:
            continue
        non_renewable[name]["amount"] = max(0.0, non_renewable[name]["amount"] - max(float(amount), 0.0))

    for name, amount in action.get("produce_resources", {}).get("renewable", {}).items():
        if name not in renewable:
            renewable[name] = {"amount": 0.0, "regen_rate": 0.0, "capacity": 100.0}
        capacity = float(renewable[name].get("capacity", 100.0))
        renewable[name]["amount"] = min(
            capacity,
            renewable[name]["amount"] + max(float(amount), 0.0),
        )

    health = next_state.setdefault("global_health", {})
    health["score"] = _clamp(float(health.get("score", 50.0)) + float(action.get("health_delta", 0.0)))

    external = next_state.setdefault("external", {})
    entities = external.setdefault("entities", [])
    artifacts = external.setdefault("artifacts", [])

    for new_entity in action.get("entities", {}).get("add", []):
        entities.append(new_entity)
    if remove_ids := set(action.get("entities", {}).get("remove", [])):
        external["entities"] = [entry for entry in entities if entry.get("id") not in remove_ids]

    for new_artifact in action.get("artifacts", {}).get("add", []):
        artifacts.append(new_artifact)
    if remove_ids := set(action.get("artifacts", {}).get("remove", [])):
        external["artifacts"] = [entry for entry in artifacts if entry.get("id") not in remove_ids]

    map_data = next_state.setdefault("map", {})
    spaces = map_data.setdefault("spaces", [])
    niches = map_data.setdefault("niches", [])
    spaces.extend(action.get("map_updates", {}).get("add_spaces", []))
    niches.extend(action.get("map_updates", {}).get("add_niches", []))

    save_world_state(next_state, state_path)
    return next_state


def tick_world(
    *,
    state: dict[str, Any] | None = None,
    state_path: Path | str | None = None,
    steps: int = 1,
) -> dict[str, Any]:
    """Advance world time and apply renewable regeneration + health drift."""

    next_state = deepcopy(state) if state is not None else load_world_state(state_path)
    tick_count = max(int(steps), 0)
    resources = next_state.get("resources", {})
    renewable = resources.get("renewable", {})

    for _ in range(tick_count):
        for payload in renewable.values():
            regen_rate = max(float(payload.get("regen_rate", 0.0)), 0.0)
            capacity = max(float(payload.get("capacity", 100.0)), 0.0)
            payload["amount"] = min(capacity, max(float(payload.get("amount", 0.0)), 0.0) + regen_rate)
        next_state["world_clock"] = int(next_state.get("world_clock", 0)) + 1

    total_capacity = 0.0
    total_amount = 0.0
    for payload in renewable.values():
        total_amount += float(payload.get("amount", 0.0))
        total_capacity += float(payload.get("capacity", 0.0))
    coverage = (total_amount / total_capacity) if total_capacity else 0.0

    pressure = _clamp((1.0 - coverage) * 100.0, minimum=0.0, maximum=1.0)
    health = next_state.setdefault("global_health", {})
    signals = health.setdefault("signals", {})
    signals["resource_pressure"] = round(pressure, 3)

    base_score = float(health.get("score", 50.0))
    drift = (coverage - 0.5) * 2.5 * tick_count
    updated_score = _clamp(base_score + drift)
    health["score"] = round(updated_score, 3)
    if drift > 0.2:
        health["trend"] = "improving"
    elif drift < -0.2:
        health["trend"] = "degrading"
    else:
        health["trend"] = "stable"

    save_world_state(next_state, state_path)
    return next_state
