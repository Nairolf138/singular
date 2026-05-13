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
                "add": [
                    {"id": "sensor-grid", "kind": "infrastructure", "integrity": 1.0}
                ],
            },
            "map_updates": {
                "add_spaces": [{"id": "delta", "kind": "frontier", "stability": 0.6}],
                "add_niches": [
                    {"id": "mining", "space_id": "delta", "specialization": "ore"}
                ],
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
    updated = apply_action_effects(
        effects, state_path=state_path, effects_path=effects_path
    )
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


def test_default_world_state_contains_structured_environment_and_symbolic_resources(
    tmp_path: Path,
) -> None:
    path = tmp_path / "mem" / "world_state.json"

    state = load_world_state(path)

    assert state["environment"]["time"]["cycle"] == "day"
    assert state["environment"]["weather"]["condition"] == "clear"
    assert state["environment"]["climate"]["type"] == "temperate"
    assert state["environment"]["biomes"]
    for resource_name in (
        "energy",
        "food_symbolic",
        "space",
        "heat",
        "information",
        "local_reputation",
    ):
        payload = state["resources"]["symbolic"][resource_name]
        assert 0.0 <= payload["amount"] <= payload["capacity"]


def test_tick_world_advances_day_night_cycle_and_dynamic_pressures(
    tmp_path: Path,
) -> None:
    path = tmp_path / "mem" / "world_state.json"
    state = load_world_state(path)
    state["environment"]["time"]["hour"] = 17
    state["resources"]["symbolic"]["information"]["amount"] = 95.0
    state["dynamics"]["relational_debt"] = 50.0

    ticked = tick_world(state=state, state_path=path, steps=2)

    assert ticked["environment"]["time"]["hour"] == 19
    assert ticked["environment"]["time"]["cycle"] == "night"
    assert ticked["environment"]["time"]["phase"] == "dusk"
    pressures = ticked["dynamics"]["pressures"]
    for pressure_name in (
        "scarcity",
        "overload",
        "competition",
        "temporary_opportunity",
    ):
        assert 0.0 <= pressures[pressure_name] <= 1.0
    assert pressures["competition"] > 0.0


def test_world_actions_update_resources_with_bounds_and_environment(
    tmp_path: Path,
) -> None:
    path = tmp_path / "mem" / "world_state.json"
    state = load_world_state(path)
    state["resources"]["symbolic"]["energy"]["amount"] = 1.0
    state["resources"]["symbolic"]["food_symbolic"]["amount"] = 79.0

    foraged = apply_action(
        {
            "action": "forage",
            "context": {
                "intensity": 2.0,
                "target_niche": "forage",
                "target_biome": "wild-edge",
            },
        },
        state=state,
        state_path=path,
    )

    assert foraged["resources"]["symbolic"]["energy"]["amount"] == 0.0
    assert foraged["resources"]["symbolic"]["food_symbolic"]["amount"] == 80.0
    assert foraged["environment"]["active_niche"] == "forage"
    assert foraged["environment"]["current_biome"] == "wild-edge"
    assert 0.0 <= foraged["dynamics"]["pressures"]["scarcity"] <= 1.0


def test_perform_action_connects_world_actions_to_effectors() -> None:
    from singular.life.effectors.core import perform_action

    result = perform_action(
        "share_resource",
        {"risk": 0.1, "rarity_pressure": 0.2, "success_bias": 0.1},
    )

    assert result.action == "share_resource"
    assert result.success is True
    assert result.energy_delta < 0.0
    assert result.world_delta["reputation"] > 0.0
    assert "world_action_effect" in result.metadata
