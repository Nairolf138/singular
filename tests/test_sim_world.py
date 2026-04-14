from pathlib import Path

from singular.environment.sim_world import (
    apply_action,
    apply_action_effects,
    load_world_state,
    map_action_type_to_effect,
    tick_world,
)


def test_load_world_state_creates_default_when_missing(tmp_path: Path) -> None:
    path = tmp_path / "mem" / "world_state.json"

    state = load_world_state(path)

    assert path.exists()
    assert state["world_clock"] == 0
    assert state["resources"]["renewable"]["solar"]["amount"] > 0


def test_apply_action_updates_resources_map_and_external(tmp_path: Path) -> None:
    path = tmp_path / "mem" / "world_state.json"
    _ = load_world_state(path)

    updated = apply_action(
        {
            "consume_resources": {
                "renewable": {"solar": 10},
                "non_renewable": {"ore": 5},
            },
            "produce_resources": {
                "renewable": {"biomass": 4},
            },
            "health_delta": -3,
            "entities": {
                "add": [{"id": "visitor-01", "type": "envoy", "stance": "friendly"}],
                "remove": ["trader-01"],
            },
            "artifacts": {
                "add": [{"id": "sensor-grid", "kind": "infrastructure", "integrity": 1.0}],
            },
            "map_updates": {
                "add_spaces": [{"id": "delta", "kind": "frontier", "stability": 0.6}],
                "add_niches": [{"id": "mining", "space_id": "delta", "specialization": "ore"}],
            },
        },
        state_path=path,
    )

    assert updated["resources"]["renewable"]["solar"]["amount"] == 60.0
    assert updated["resources"]["non_renewable"]["ore"]["amount"] == 75.0
    assert updated["global_health"]["score"] == 79.0
    assert any(e["id"] == "visitor-01" for e in updated["external"]["entities"])
    assert all(e["id"] != "trader-01" for e in updated["external"]["entities"])
    assert any(s["id"] == "delta" for s in updated["map"]["spaces"])


def test_tick_world_regenerates_and_updates_health(tmp_path: Path) -> None:
    path = tmp_path / "mem" / "world_state.json"
    state = load_world_state(path)
    state["resources"]["renewable"]["solar"]["amount"] = 20.0
    state["resources"]["renewable"]["biomass"]["amount"] = 10.0

    ticked = tick_world(state=state, state_path=path, steps=2)

    assert ticked["world_clock"] == 2
    assert ticked["resources"]["renewable"]["solar"]["amount"] == 30.0
    assert ticked["resources"]["renewable"]["biomass"]["amount"] == 16.0
    assert ticked["global_health"]["trend"] == "degrading"
    assert 0.0 <= ticked["global_health"]["signals"]["resource_pressure"] <= 1.0


def test_apply_action_effects_writes_atomic_cumulative_effects(tmp_path: Path) -> None:
    state_path = tmp_path / "mem" / "world_state.json"
    effects_path = tmp_path / "mem" / "world_effects.json"
    _ = load_world_state(state_path)
    effects = [
        map_action_type_to_effect("mutation.applied"),
        map_action_type_to_effect("resource.conflict"),
    ]
    updated = apply_action_effects(effects, state_path=state_path, effects_path=effects_path)
    assert effects_path.exists()
    assert "global_health" in updated
    ledger = effects_path.read_text(encoding="utf-8")
    assert '"last_effect_count": 2' in ledger


def test_overexploitation_schedules_and_triggers_delayed_crisis(tmp_path: Path) -> None:
    path = tmp_path / "mem" / "world_state.json"
    state = load_world_state(path)
    over = map_action_type_to_effect("resource.overexploitation")
    updated = apply_action(over, state=state, state_path=path)
    assert updated["dynamics"]["ecological_debt"] > 0.0
    assert updated["dynamics"]["delayed_events"]

    ticked = tick_world(state=updated, state_path=path, steps=2)
    fired = ticked["global_health"].get("delayed_events_fired", [])
    assert any(entry.get("kind") == "crisis" for entry in fired)
    assert ticked["global_health"]["signals"]["delayed_risk"] >= 0.0
