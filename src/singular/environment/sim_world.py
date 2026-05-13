"""Simulation world state backed by ``mem/world_state.json``.

The module is intentionally data-driven: callers can pass generic action
payloads to evolve the world without changing Python code.
"""

from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_BASE_DIR = Path(os.environ.get("SINGULAR_HOME", "."))
DEFAULT_WORLD_STATE_PATH = _BASE_DIR / "mem" / "world_state.json"
DEFAULT_WORLD_EFFECTS_PATH = _BASE_DIR / "mem" / "world_effects.json"

RESOURCE_GROUPS = ("renewable", "non_renewable", "symbolic")
WORLD_ACTION_NAMES = {
    "move",
    "rest",
    "forage",
    "cooperate",
    "compete",
    "share_resource",
    "avoid_threat",
}

ACTION_TYPE_TO_WORLD_EFFECT: dict[str, dict[str, Any]] = {
    "mutation.applied": {
        "produce_resources": {"renewable": {"biomass": 1.0}},
        "health_delta": 0.4,
    },
    "mutation.rejected": {
        "consume_resources": {"renewable": {"solar": 0.8}},
        "health_delta": -0.4,
    },
    "resource.competition.granted": {
        "consume_resources": {"renewable": {"solar": 0.5}},
        "health_delta": 0.1,
    },
    "resource.competition.denied": {
        "health_delta": -0.2,
    },
    "resource.cooperation": {
        "produce_resources": {"renewable": {"solar": 0.6}},
        "health_delta": 0.3,
        "relational_debt_delta": -1.0,
    },
    "resource.conflict": {
        "consume_resources": {"renewable": {"biomass": 0.7}},
        "health_delta": -0.5,
        "ecological_debt_delta": 2.5,
        "relational_debt_delta": 2.0,
    },
    "resource.overexploitation": {
        "consume_resources": {"renewable": {"biomass": 1.6, "solar": 0.9}},
        "health_delta": -0.7,
        "ecological_debt_delta": 5.0,
        "delayed_events": [
            {
                "kind": "crisis",
                "label": "ecosystem-backlash",
                "in_ticks": 2,
                "effect": {
                    "consume_resources": {"renewable": {"biomass": 2.0}},
                    "health_delta": -1.1,
                    "ecological_debt_delta": 2.0,
                },
            }
        ],
    },
    "skill.execution.succeeded": {
        "produce_resources": {"renewable": {"solar": 0.4}},
        "health_delta": 0.2,
    },
    "skill.execution.failed": {
        "consume_resources": {"renewable": {"solar": 0.4}},
        "health_delta": -0.3,
    },
    "skill.execution.no_compatible": {
        "health_delta": -0.1,
    },
}

WORLD_ACTION_EFFECTS: dict[str, dict[str, Any]] = {
    "move": {
        "consume_resources": {
            "symbolic": {"energy": 4.0, "space": 1.0, "information": 0.5}
        },
        "produce_resources": {"symbolic": {"information": 2.0}},
        "health_delta": -0.1,
        "pressure_delta": {"overload": 0.01, "temporary_opportunity": 0.03},
    },
    "rest": {
        "consume_resources": {"symbolic": {"space": 2.0, "heat": 1.0}},
        "produce_resources": {"symbolic": {"energy": 8.0}},
        "health_delta": 0.6,
        "pressure_delta": {"overload": -0.08, "competition": -0.02},
    },
    "forage": {
        "consume_resources": {"symbolic": {"energy": 5.0, "space": 1.0}},
        "produce_resources": {
            "renewable": {"biomass": 3.0},
            "symbolic": {"food_symbolic": 9.0, "information": 1.0},
        },
        "health_delta": 0.2,
        "ecological_debt_delta": 0.4,
        "pressure_delta": {"scarcity": -0.05, "competition": 0.02},
    },
    "cooperate": {
        "consume_resources": {"symbolic": {"energy": 2.0, "information": 1.0}},
        "produce_resources": {
            "symbolic": {"local_reputation": 6.0, "information": 3.0}
        },
        "health_delta": 0.4,
        "relational_debt_delta": -2.0,
        "pressure_delta": {"competition": -0.06, "temporary_opportunity": 0.05},
    },
    "compete": {
        "consume_resources": {"symbolic": {"energy": 6.0, "local_reputation": 2.0}},
        "produce_resources": {"symbolic": {"space": 4.0}},
        "health_delta": -0.3,
        "relational_debt_delta": 3.0,
        "pressure_delta": {"competition": 0.12, "scarcity": 0.04},
    },
    "share_resource": {
        "consume_resources": {"symbolic": {"food_symbolic": 4.0, "energy": 1.0}},
        "produce_resources": {"symbolic": {"local_reputation": 8.0}},
        "health_delta": 0.3,
        "relational_debt_delta": -3.0,
        "pressure_delta": {"competition": -0.08, "temporary_opportunity": 0.03},
    },
    "avoid_threat": {
        "consume_resources": {"symbolic": {"energy": 3.0, "information": 1.0}},
        "produce_resources": {"symbolic": {"space": 2.0}},
        "health_delta": 0.1,
        "pressure_delta": {"overload": -0.04, "temporary_opportunity": -0.02},
    },
}

for _name, _effect in WORLD_ACTION_EFFECTS.items():
    ACTION_TYPE_TO_WORLD_EFFECT[f"world.{_name}"] = _effect


def default_world_state() -> dict[str, Any]:
    """Return the default world model."""

    return {
        "world_clock": 0,
        "environment": {
            "time": {
                "tick": 0,
                "hour": 6,
                "day": 1,
                "cycle": "day",
                "phase": "dawn",
            },
            "weather": {
                "condition": "clear",
                "temperature": 21.0,
                "humidity": 0.45,
                "wind": 0.2,
            },
            "climate": {
                "type": "temperate",
                "season": "spring",
                "stability": 0.82,
            },
            "biomes": [
                {
                    "id": "core-garden",
                    "kind": "urban-garden",
                    "abundance": 0.72,
                    "thermal_profile": "mild",
                },
                {
                    "id": "wild-edge",
                    "kind": "edge-wilds",
                    "abundance": 0.54,
                    "thermal_profile": "variable",
                },
            ],
            "current_biome": "core-garden",
            "active_niche": "research",
        },
        "map": {
            "spaces": [
                {"id": "core", "kind": "hub", "stability": 0.9},
                {"id": "wilds", "kind": "exploration", "stability": 0.7},
            ],
            "niches": [
                {"id": "craft", "space_id": "core", "specialization": "fabrication"},
                {"id": "research", "space_id": "core", "specialization": "insight"},
                {"id": "forage", "space_id": "wilds", "specialization": "biomass"},
                {"id": "shelter", "space_id": "core", "specialization": "recovery"},
            ],
        },
        "resources": {
            "renewable": {
                "solar": {"amount": 70.0, "regen_rate": 5.0, "capacity": 100.0},
                "biomass": {"amount": 45.0, "regen_rate": 3.0, "capacity": 75.0},
            },
            "non_renewable": {
                "ore": {"amount": 80.0, "capacity": 80.0},
                "rare_earth": {"amount": 20.0, "capacity": 20.0},
            },
            "symbolic": {
                "energy": {"amount": 65.0, "regen_rate": 2.0, "capacity": 100.0},
                "food_symbolic": {"amount": 42.0, "regen_rate": 1.0, "capacity": 80.0},
                "space": {"amount": 55.0, "regen_rate": 0.5, "capacity": 100.0},
                "heat": {"amount": 50.0, "regen_rate": 0.8, "capacity": 100.0},
                "information": {"amount": 35.0, "regen_rate": 1.5, "capacity": 100.0},
                "local_reputation": {
                    "amount": 30.0,
                    "regen_rate": 0.2,
                    "capacity": 100.0,
                },
            },
        },
        "external": {
            "entities": [
                {"id": "trader-01", "type": "merchant", "stance": "neutral"},
                {"id": "observer-01", "type": "monitor", "stance": "supportive"},
            ],
            "artifacts": [{"id": "relay", "kind": "communication", "integrity": 0.95}],
        },
        "global_health": {
            "score": 82.0,
            "trend": "stable",
            "signals": {
                "resource_pressure": 0.2,
                "cohesion": 0.85,
                "ecological_debt": 0.0,
                "relational_debt": 0.0,
                "delayed_risk": 0.0,
            },
        },
        "dynamics": {
            "ecological_debt": 0.0,
            "relational_debt": 0.0,
            "delayed_events": [],
            "pressures": {
                "scarcity": 0.2,
                "overload": 0.1,
                "competition": 0.2,
                "temporary_opportunity": 0.25,
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


def _resource_payload(
    resources: dict[str, Any], group: str, name: str
) -> dict[str, Any]:
    group_payload = resources.setdefault(group, {})
    default_capacity = 100.0
    return group_payload.setdefault(
        name,
        {"amount": 0.0, "regen_rate": 0.0, "capacity": default_capacity},
    )


def _iter_resource_payloads(resources: dict[str, Any]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for group_name in RESOURCE_GROUPS:
        group = resources.get(group_name, {})
        if isinstance(group, dict):
            payloads.extend(
                payload for payload in group.values() if isinstance(payload, dict)
            )
    return payloads


def _merge_world_action(action: dict[str, Any]) -> dict[str, Any]:
    action_name = (
        action.get("action") or action.get("world_action") or action.get("type")
    )
    if action_name not in WORLD_ACTION_NAMES:
        return deepcopy(action)
    merged = deepcopy(world_action_to_effect(str(action_name), action.get("context")))
    for key, value in action.items():
        if key in {"action", "world_action", "type", "context"}:
            continue
        if key in {
            "consume_resources",
            "produce_resources",
            "entities",
            "artifacts",
            "map_updates",
        } and isinstance(value, dict):
            target = merged.setdefault(key, {})
            if isinstance(target, dict):
                for subkey, subvalue in value.items():
                    target[subkey] = subvalue
        else:
            merged[key] = value
    return merged


def _apply_action_to_state(
    next_state: dict[str, Any], action: dict[str, Any]
) -> dict[str, Any]:
    action = _merge_world_action(action)
    resources = next_state.setdefault("resources", {})

    for resource_type, payload in action.get("consume_resources", {}).items():
        if not isinstance(payload, dict):
            continue
        for name, amount in payload.items():
            existing = resources.get(resource_type, {}).get(name)
            if not isinstance(existing, dict):
                continue
            existing["amount"] = max(
                0.0, float(existing.get("amount", 0.0)) - max(float(amount), 0.0)
            )

    for resource_type, payload in action.get("produce_resources", {}).items():
        if not isinstance(payload, dict):
            continue
        for name, amount in payload.items():
            existing = _resource_payload(resources, resource_type, name)
            capacity = float(existing.get("capacity", 100.0))
            existing["amount"] = min(
                capacity,
                float(existing.get("amount", 0.0)) + max(float(amount), 0.0),
            )

    health = next_state.setdefault("global_health", {})
    health["score"] = _clamp(
        float(health.get("score", 50.0)) + float(action.get("health_delta", 0.0))
    )
    dynamics = next_state.setdefault("dynamics", {})
    ecological_debt = float(dynamics.get("ecological_debt", 0.0)) + float(
        action.get("ecological_debt_delta", 0.0)
    )
    relational_debt = float(dynamics.get("relational_debt", 0.0)) + float(
        action.get("relational_debt_delta", 0.0)
    )
    dynamics["ecological_debt"] = _clamp(ecological_debt, minimum=0.0, maximum=100.0)
    dynamics["relational_debt"] = _clamp(relational_debt, minimum=0.0, maximum=100.0)
    pressures = dynamics.setdefault("pressures", {})
    for name, delta in action.get("pressure_delta", {}).items():
        pressures[name] = round(
            _clamp(float(pressures.get(name, 0.0)) + float(delta), 0.0, 1.0), 3
        )
    delayed_events = dynamics.setdefault("delayed_events", [])
    for delayed_event in action.get("delayed_events", []):
        if not isinstance(delayed_event, dict):
            continue
        delayed_events.append(
            {
                "kind": str(delayed_event.get("kind", "unknown")),
                "label": str(delayed_event.get("label", "scheduled-effect")),
                "in_ticks": max(int(delayed_event.get("in_ticks", 1)), 1),
                "effect": deepcopy(delayed_event.get("effect", {})),
            }
        )

    environment = next_state.setdefault("environment", {})
    for key, value in action.get("environment_updates", {}).items():
        if isinstance(value, dict) and isinstance(environment.get(key), dict):
            environment[key].update(value)
        else:
            environment[key] = value

    external = next_state.setdefault("external", {})
    entities = external.setdefault("entities", [])
    artifacts = external.setdefault("artifacts", [])

    for new_entity in action.get("entities", {}).get("add", []):
        entities.append(new_entity)
    if remove_ids := set(action.get("entities", {}).get("remove", [])):
        external["entities"] = [
            entry for entry in entities if entry.get("id") not in remove_ids
        ]

    for new_artifact in action.get("artifacts", {}).get("add", []):
        artifacts.append(new_artifact)
    if remove_ids := set(action.get("artifacts", {}).get("remove", [])):
        external["artifacts"] = [
            entry for entry in artifacts if entry.get("id") not in remove_ids
        ]

    map_data = next_state.setdefault("map", {})
    spaces = map_data.setdefault("spaces", [])
    niches = map_data.setdefault("niches", [])
    spaces.extend(action.get("map_updates", {}).get("add_spaces", []))
    niches.extend(action.get("map_updates", {}).get("add_niches", []))
    return next_state


def world_action_to_effect(action: str, context: Any | None = None) -> dict[str, Any]:
    """Return the world-state effect payload for a high-level world action."""

    if action not in WORLD_ACTION_EFFECTS:
        return {}
    effect = deepcopy(WORLD_ACTION_EFFECTS[action])
    if not isinstance(context, dict):
        return effect

    intensity = _clamp(float(context.get("intensity", 1.0)), 0.0, 3.0)
    if intensity != 1.0:
        for family in ("consume_resources", "produce_resources"):
            for payload in effect.get(family, {}).values():
                if isinstance(payload, dict):
                    for name, amount in list(payload.items()):
                        payload[name] = float(amount) * intensity
        if "health_delta" in effect:
            effect["health_delta"] = float(effect["health_delta"]) * intensity
    target_niche = context.get("target_niche")
    if target_niche:
        effect.setdefault("environment_updates", {})["active_niche"] = str(target_niche)
    target_biome = context.get("target_biome")
    if target_biome:
        effect.setdefault("environment_updates", {})["current_biome"] = str(
            target_biome
        )
    return effect


def map_action_type_to_effect(
    action_type: str, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    if action_type in WORLD_ACTION_NAMES:
        template = world_action_to_effect(action_type, payload)
    else:
        template = deepcopy(ACTION_TYPE_TO_WORLD_EFFECT.get(action_type, {}))
    if not payload:
        return template
    for key in (
        "consume_resources",
        "produce_resources",
        "entities",
        "artifacts",
        "map_updates",
        "environment_updates",
        "pressure_delta",
    ):
        incoming = payload.get(key)
        if not isinstance(incoming, dict):
            continue
        existing = template.setdefault(key, {})
        if isinstance(existing, dict):
            for subkey, subvalue in incoming.items():
                existing[subkey] = subvalue
    for numeric_key in (
        "health_delta",
        "ecological_debt_delta",
        "relational_debt_delta",
    ):
        if numeric_key in payload:
            template[numeric_key] = float(payload[numeric_key])
    return template


def _merge_action_effect(
    total: dict[str, Any], effect: dict[str, Any]
) -> dict[str, Any]:
    merged = deepcopy(total)
    merged["health_delta"] = float(merged.get("health_delta", 0.0)) + float(
        effect.get("health_delta", 0.0)
    )
    merged["ecological_debt_delta"] = float(
        merged.get("ecological_debt_delta", 0.0)
    ) + float(effect.get("ecological_debt_delta", 0.0))
    merged["relational_debt_delta"] = float(
        merged.get("relational_debt_delta", 0.0)
    ) + float(effect.get("relational_debt_delta", 0.0))
    for family in ("consume_resources", "produce_resources"):
        family_dst = merged.setdefault(family, {})
        family_src = effect.get(family, {})
        if not isinstance(family_src, dict):
            continue
        for resource_type, payload in family_src.items():
            if not isinstance(payload, dict):
                continue
            dst_payload = family_dst.setdefault(resource_type, {})
            for name, amount in payload.items():
                dst_payload[name] = float(dst_payload.get(name, 0.0)) + float(amount)
    return merged


def apply_action_effects(
    effects: list[dict[str, Any]],
    *,
    state: dict[str, Any] | None = None,
    state_path: Path | str | None = None,
    effects_path: Path | str | None = None,
) -> dict[str, Any]:
    next_state = deepcopy(state) if state is not None else load_world_state(state_path)
    cumulative: dict[str, Any] = {"health_delta": 0.0}
    for effect in effects:
        _apply_action_to_state(next_state, effect)
        cumulative = _merge_action_effect(cumulative, _merge_world_action(effect))
    save_world_state(next_state, state_path)

    ledger_path = (
        Path(effects_path) if effects_path is not None else DEFAULT_WORLD_EFFECTS_PATH
    )
    ledger = {
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "cumulative_effect": cumulative,
        "last_effect_count": len(effects),
    }
    _atomic_write_json(ledger_path, ledger)
    return next_state


def apply_action(
    action: dict[str, Any],
    *,
    state: dict[str, Any] | None = None,
    state_path: Path | str | None = None,
) -> dict[str, Any]:
    """Apply a generic action payload to the world and persist it.

    Supported keys include ``consume_resources``, ``produce_resources``,
    ``health_delta``, ``entities`` and ``artifacts`` (with ``add``/``remove``),
    ``map_updates`` for adding spaces/niches, and high-level world actions via
    ``{"action": "forage"}`` style payloads.
    """

    next_state = deepcopy(state) if state is not None else load_world_state(state_path)

    _apply_action_to_state(next_state, action)

    save_world_state(next_state, state_path)
    return next_state


def _time_labels(hour: int) -> tuple[str, str]:
    if 5 <= hour < 8:
        return "day", "dawn"
    if 8 <= hour < 18:
        return "day", "daylight"
    if 18 <= hour < 21:
        return "night", "dusk"
    return "night", "night"


def _advance_environment(next_state: dict[str, Any]) -> None:
    environment = next_state.setdefault("environment", {})
    time_data = environment.setdefault("time", {})
    hour = (int(time_data.get("hour", 0)) + 1) % 24
    if hour == 0:
        time_data["day"] = int(time_data.get("day", 1)) + 1
    cycle, phase = _time_labels(hour)
    time_data.update(
        {
            "tick": int(next_state.get("world_clock", 0)),
            "hour": hour,
            "cycle": cycle,
            "phase": phase,
        }
    )

    weather = environment.setdefault("weather", {})
    climate = environment.setdefault("climate", {})
    season = str(climate.get("season", "spring"))
    seasonal_baseline = {
        "winter": 8.0,
        "spring": 18.0,
        "summer": 27.0,
        "autumn": 15.0,
    }.get(season, 18.0)
    day_bonus = 4.0 if cycle == "day" else -3.0
    weather["temperature"] = round(seasonal_baseline + day_bonus, 2)
    weather["condition"] = "clear" if cycle == "day" else "cool-night"
    weather["humidity"] = round(
        _clamp(
            float(weather.get("humidity", 0.45))
            + (0.01 if cycle == "night" else -0.01),
            0.2,
            0.9,
        ),
        3,
    )


def _recompute_pressures(next_state: dict[str, Any], coverage: float) -> None:
    dynamics = next_state.setdefault("dynamics", {})
    pressures = dynamics.setdefault("pressures", {})
    relational_debt = _clamp(float(dynamics.get("relational_debt", 0.0)), 0.0, 100.0)
    ecological_debt = _clamp(float(dynamics.get("ecological_debt", 0.0)), 0.0, 100.0)
    resources = next_state.get("resources", {})
    symbolic = resources.get("symbolic", {}) if isinstance(resources, dict) else {}
    information = symbolic.get("information", {}) if isinstance(symbolic, dict) else {}
    info_capacity = float(information.get("capacity", 100.0)) or 100.0
    info_load = float(information.get("amount", 0.0)) / info_capacity
    opportunity = float(pressures.get("temporary_opportunity", 0.25))
    pressures["scarcity"] = round(_clamp(1.0 - coverage, 0.0, 1.0), 3)
    pressures["competition"] = round(
        _clamp((relational_debt / 100.0) + (1.0 - coverage) * 0.4, 0.0, 1.0), 3
    )
    pressures["overload"] = round(
        _clamp((ecological_debt / 100.0) * 0.5 + max(0.0, info_load - 0.7), 0.0, 1.0), 3
    )
    pressures["temporary_opportunity"] = round(
        _clamp(opportunity * 0.95 + (0.05 if coverage > 0.55 else -0.02), 0.0, 1.0), 3
    )


def tick_world(
    *,
    state: dict[str, Any] | None = None,
    state_path: Path | str | None = None,
    steps: int = 1,
) -> dict[str, Any]:
    """Advance world time and apply renewable regeneration + health drift."""

    next_state = deepcopy(state) if state is not None else load_world_state(state_path)
    tick_count = max(int(steps), 0)
    resources = next_state.setdefault("resources", {})
    dynamics = next_state.setdefault("dynamics", {})
    ecological_debt = _clamp(
        float(dynamics.get("ecological_debt", 0.0)), minimum=0.0, maximum=100.0
    )
    relational_debt = _clamp(
        float(dynamics.get("relational_debt", 0.0)), minimum=0.0, maximum=100.0
    )
    delayed_events = list(dynamics.get("delayed_events", []))
    fired_delayed_events: list[dict[str, Any]] = []

    for _ in range(tick_count):
        for group_name in ("renewable", "symbolic"):
            group = resources.get(group_name, {})
            if not isinstance(group, dict):
                continue
            for payload in group.values():
                if not isinstance(payload, dict):
                    continue
                regen_rate = max(float(payload.get("regen_rate", 0.0)), 0.0)
                capacity = max(float(payload.get("capacity", 100.0)), 0.0)
                regen_penalty = (ecological_debt / 100.0) * 0.4
                effective_regen = regen_rate * max(0.1, 1.0 - regen_penalty)
                payload["amount"] = min(
                    capacity,
                    max(float(payload.get("amount", 0.0)), 0.0) + effective_regen,
                )
        matured: list[dict[str, Any]] = []
        pending: list[dict[str, Any]] = []
        for entry in delayed_events:
            if not isinstance(entry, dict):
                continue
            remaining = int(entry.get("in_ticks", 1)) - 1
            updated_entry = dict(entry)
            updated_entry["in_ticks"] = remaining
            if remaining <= 0:
                matured.append(updated_entry)
            else:
                pending.append(updated_entry)
        for matured_entry in matured:
            fired_delayed_events.append(
                {
                    "kind": str(matured_entry.get("kind", "unknown")),
                    "label": str(matured_entry.get("label", "scheduled-effect")),
                }
            )
            effect_payload = matured_entry.get("effect", {})
            if isinstance(effect_payload, dict):
                _apply_action_to_state(next_state, effect_payload)
        delayed_events = pending
        dynamics["delayed_events"] = delayed_events
        next_state["world_clock"] = int(next_state.get("world_clock", 0)) + 1
        _advance_environment(next_state)

    total_capacity = 0.0
    total_amount = 0.0
    for payload in _iter_resource_payloads(resources):
        total_amount += float(payload.get("amount", 0.0))
        total_capacity += float(payload.get("capacity", 0.0))
    coverage = (total_amount / total_capacity) if total_capacity else 0.0
    renewable_capacity = 0.0
    renewable_amount = 0.0
    renewable = resources.get("renewable", {})
    if isinstance(renewable, dict):
        for payload in renewable.values():
            if not isinstance(payload, dict):
                continue
            renewable_amount += float(payload.get("amount", 0.0))
            renewable_capacity += float(payload.get("capacity", 0.0))
    vital_coverage = (
        (renewable_amount / renewable_capacity) if renewable_capacity else coverage
    )

    pressure = _clamp(1.0 - vital_coverage, minimum=0.0, maximum=1.0)
    health = next_state.setdefault("global_health", {})
    signals = health.setdefault("signals", {})
    signals["resource_pressure"] = round(pressure, 3)
    dynamics = next_state.setdefault("dynamics", {})
    ecological_debt = _clamp(
        float(dynamics.get("ecological_debt", 0.0)), minimum=0.0, maximum=100.0
    )
    relational_debt = _clamp(
        float(dynamics.get("relational_debt", 0.0)), minimum=0.0, maximum=100.0
    )
    delayed_risk = _clamp(
        len(dynamics.get("delayed_events", [])) / 8.0, minimum=0.0, maximum=1.0
    )
    signals["ecological_debt"] = round(ecological_debt / 100.0, 3)
    signals["relational_debt"] = round(relational_debt / 100.0, 3)
    signals["delayed_risk"] = round(delayed_risk, 3)
    _recompute_pressures(next_state, coverage)
    if fired_delayed_events:
        health["delayed_events_fired"] = fired_delayed_events
    else:
        health.pop("delayed_events_fired", None)

    base_score = float(health.get("score", 50.0))
    debt_drag = ((ecological_debt * 0.012) + (relational_debt * 0.009)) * tick_count
    drift = ((vital_coverage - 0.5) * 2.5 * tick_count) - debt_drag
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
