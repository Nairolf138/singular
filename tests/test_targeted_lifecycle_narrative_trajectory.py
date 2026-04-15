from __future__ import annotations

import json
import random
from pathlib import Path

from fastapi_stub import TestClient

from singular.dashboard import create_app
from singular.environment import sim_world
from singular.goals.quest_generation import generate_quests
from singular.life.death import DeathMonitor
from singular.life.loop import CHECKPOINT_VERSION, load_checkpoint
from singular.organisms.birth import birth
from singular.organisms.status import status
from singular.self_narrative import SCHEMA_VERSION, load, update_from_signals


class _DummyPsyche:
    last_mood = None
    curiosity = 0.5
    patience = 0.5
    playfulness = 0.5
    optimism = 0.5
    resilience = 0.5


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_targeted_lifecycle_birth_introspection_goals_world_action_death(
    tmp_path: Path,
    monkeypatch,
) -> None:
    life_home = tmp_path / "life"
    monkeypatch.setenv("SINGULAR_HOME", str(life_home))

    # naissance (seed fixe)
    birth(seed=123, home=life_home)
    birth_events = _read_jsonl(life_home / "mem" / "life_events.jsonl")
    assert birth_events
    assert birth_events[-1]["event_type"] == "birth_certificate"

    # introspection narrative persistée
    narrative = update_from_signals(
        {
            "current_heading": "Stabiliser les cycles décisionnels.",
            "regrets_and_pride": {"significant_successes": ["naissance stable"]},
        },
        path=life_home / "mem" / "self_narrative.json",
    )
    assert narrative.current_heading == "Stabiliser les cycles décisionnels."

    # génération de buts pilotée par état interne/externe
    world_state = sim_world.load_world_state(life_home / "mem" / "world_state.json")
    generated = generate_quests(
        psyche_traits={"curiosity": 0.7, "optimism": 0.4, "resilience": 0.4},
        outcomes_history={"recent_successes": 0, "recent_failures": 4},
        value_performance_tension={"score": 0.8},
        world_state=world_state["global_health"]["signals"],
        resources={"energy": 35, "food": 30, "warmth": 40},
    )
    assert generated
    assert generated[0].priority >= generated[-1].priority

    # action monde
    before_score = float(world_state["global_health"]["score"])
    conflict_effect = sim_world.map_action_type_to_effect("resource.conflict")
    updated_world = sim_world.apply_action_effects(
        [conflict_effect],
        state_path=life_home / "mem" / "world_state.json",
        effects_path=life_home / "mem" / "world_effects.json",
    )
    assert float(updated_world["global_health"]["score"]) < before_score

    # mort (invariant raison terminale)
    monitor = DeathMonitor(max_failures=2)
    psyche = _DummyPsyche()
    dead, reason = monitor.check(
        iteration=1,
        psyche=psyche,
        action_succeeded=False,
        resources=1.0,
    )
    assert dead is False
    dead, reason = monitor.check(
        iteration=2,
        psyche=psyche,
        action_succeeded=False,
        resources=1.0,
    )
    assert dead is True
    assert reason == "too many failures"


def test_narrative_files_persist_and_reload_with_fixed_seed(tmp_path: Path, monkeypatch) -> None:
    life_home = tmp_path / "life"
    monkeypatch.setenv("SINGULAR_HOME", str(life_home))
    birth(seed=7, home=life_home)

    narrative_path = life_home / "mem" / "self_narrative.json"
    update_from_signals(
        {
            "identity": {"name": "Nova"},
            "current_heading": "Documenter une trajectoire explicable.",
            "life_periods": [{"title": "Boot", "highlights": ["seed=7"]}],
        },
        path=narrative_path,
    )

    reloaded = load(narrative_path)
    assert reloaded.identity.name == "Nova"
    assert reloaded.current_heading == "Documenter une trajectoire explicable."
    assert reloaded.life_periods[-1].title == "Boot"

    biography_payload = json.loads((life_home / "mem" / "biography.json").read_text(encoding="utf-8"))
    assert biography_payload["birth_certificate"]["event_type"] == "birth_certificate"
    assert biography_payload["self_summaries"]


def test_schema_invariants_and_migrations_for_narrative_and_checkpoint(tmp_path: Path) -> None:
    narrative_path = tmp_path / "mem" / "self_narrative.json"
    narrative_path.parent.mkdir(parents=True, exist_ok=True)
    narrative_path.write_text(
        json.dumps(
            {
                "schema_version": 0,
                "identity": {"name": "Legacy"},
                "trait_trends": {"curiosity": {"value": 2.5, "trend": "weird"}},
                "unexpected": {"keep": False},
            }
        ),
        encoding="utf-8",
    )

    migrated = load(narrative_path)
    assert migrated.schema_version == SCHEMA_VERSION
    assert set(migrated.trait_trends.keys()) == {
        "curiosity",
        "patience",
        "playfulness",
        "optimism",
        "resilience",
    }
    assert migrated.trait_trends["curiosity"].value == 1.0
    assert migrated.trait_trends["curiosity"].trend == "stable"

    checkpoint_path = tmp_path / "life_checkpoint.json"
    checkpoint_path.write_text(
        json.dumps({"version": 0, "iteration": 5, "unknown_field": "ignored"}),
        encoding="utf-8",
    )
    checkpoint = load_checkpoint(checkpoint_path)
    assert checkpoint.version == CHECKPOINT_VERSION
    assert checkpoint.iteration == 5


def test_status_and_dashboard_expose_trajectory_events(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "trajectory.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-04-12T10:00:00+00:00",
                        "event": "quest",
                        "objective": "coherence",
                        "objective_weights": {"coherence": 0.40},
                        "score_new": 1.0,
                        "ok": True,
                        "health": {"score": 72.0},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-04-12T10:05:00+00:00",
                        "event": "consciousness",
                        "objective": "coherence",
                        "self_narrative_event": "self_narrative.updated",
                        "objective_weights": {"coherence": 0.72},
                        "score_new": 1.2,
                        "ok": True,
                        "health": {"score": 74.0},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-04-12T10:08:00+00:00",
                        "event": "death",
                        "objective": "coherence",
                        "score_new": 0.9,
                        "ok": False,
                        "health": {"score": 12.0},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    mem_dir = tmp_path / "mem"
    mem_dir.mkdir()
    (mem_dir / "quests_state.json").write_text(
        json.dumps(
            {
                "active": [{"name": "coherence"}],
                "paused": [{"name": "latency"}],
                "completed": [{"name": "stability"}],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))
    monkeypatch.setattr("singular.organisms.status.RUNS_DIR", runs_dir)
    monkeypatch.setattr(
        "singular.organisms.status.Psyche.load_state",
        staticmethod(lambda: _DummyPsyche()),
    )

    status(output_format="json")
    payload = json.loads(capsys.readouterr().out)
    assert payload["trajectory"]["objectives"]["counts"] == {
        "in_progress": 1,
        "abandoned": 1,
        "completed": 1,
    }
    assert payload["trajectory"]["priority_changes"]
    assert payload["trajectory"]["objective_narrative_links"]
    assert payload["trajectory"]["objective_narrative_links"][-1]["event"] in {
        "death",
        "self_narrative.updated",
    }

    app = create_app(runs_dir=runs_dir, psyche_file=tmp_path / "mem" / "psyche.json")
    client = TestClient(app)
    cockpit = client.get("/api/cockpit").json()
    assert cockpit["trajectory"]["objectives"]["counts"]["in_progress"] == 1
    assert cockpit["trajectory"]["priority_changes"]
