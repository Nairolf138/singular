import json
from pathlib import Path

from singular.events import EventBus
from singular.organisms.birth import birth
from singular.skills.runtime import SkillRuntime


def _deterministic_sandbox(source: str):
    namespace: dict = {}
    exec(source, namespace, namespace)
    return namespace["result"]


def test_birth_perception_decision_action_consequence_memory(
    monkeypatch, tmp_path: Path
) -> None:
    """Exercise one static path through existing runtime integration points."""

    monkeypatch.setattr("singular.skills.runtime.sandbox.run", _deterministic_sandbox)
    home = tmp_path / "living"
    birth(seed=7, home=home, name="Ada", starter_profile="living")

    events: list[str] = []
    bus = EventBus()
    for event_type in (
        "skill.execution.succeeded",
        "world.effect.applied",
        "living.stage.completed",
    ):
        bus.subscribe(event_type, lambda event: events.append(event.event_type))
    runtime = SkillRuntime(skills_dir=home / "skills", mem_dir=home / "mem", bus=bus)

    perception = runtime.execute_best_skill(
        {"name": "perceive", "capabilities": ["living.observation"]}, {}
    )
    decision = runtime.execute_best_skill(
        {"name": "decide", "capabilities": ["living.goal_selection"]}, {}
    )
    action = runtime.execute_best_skill(
        {"name": "act", "capabilities": ["living.action"]},
        {"action": "inspect"},
    )

    assert [perception.output, decision.output, action.output] == [1.0, 1.0, 1.0]
    assert events.count("living.stage.completed") == 3
    assert events.count("world.effect.applied") == 3
    world_effects = json.loads((home / "mem" / "world_effects.json").read_text())
    assert world_effects["last_effect_count"] == 1
    episodes = [
        json.loads(line)
        for line in (home / "mem" / "episodic.jsonl").read_text().splitlines()
    ]
    assert [episode["task"] for episode in episodes] == ["perceive", "decide", "act"]
    assert all(episode["event"] == "living_skill_completed" for episode in episodes)
