from pathlib import Path

from singular.events import EventBus
from singular.orchestrator.service import (
    LifecyclePhase,
    OrchestratorConfig,
    OrchestratorService,
    SchedulerConfig,
)


def test_orchestrator_tick_persists_state(monkeypatch, tmp_path: Path) -> None:
    life = tmp_path / "life"
    (life / "skills").mkdir(parents=True)
    (life / "skills" / "a.py").write_text("result = 1", encoding="utf-8")

    monkeypatch.setenv("SINGULAR_HOME", str(life))

    bus = EventBus()
    service = OrchestratorService(
        config=OrchestratorConfig(
            scheduler=SchedulerConfig(
                veille_seconds=0.1,
                action_seconds=0.1,
                introspection_seconds=0.1,
                sommeil_seconds=0.1,
            ),
            dry_run=True,
        ),
        bus=bus,
    )

    next_phase = service.tick()

    assert next_phase == LifecyclePhase.ACTION
    state_path = life / "mem" / "orchestrator_state.json"
    assert state_path.exists()
    payload = state_path.read_text(encoding="utf-8")
    assert "current_phase" in payload


def test_orchestrator_detects_external_stimulus(monkeypatch, tmp_path: Path) -> None:
    life = tmp_path / "life"
    (life / "skills").mkdir(parents=True)
    (life / "runs").mkdir(parents=True)

    monkeypatch.setenv("SINGULAR_HOME", str(life))

    bus = EventBus()
    service = OrchestratorService(config=OrchestratorConfig(dry_run=True), bus=bus)

    assert service._external_stimulus_detected() is True
    (life / "runs" / "x.jsonl").write_text("{}\n", encoding="utf-8")
    assert service._external_stimulus_detected() is True


def test_orchestrator_triggers_and_settles_quest(monkeypatch, tmp_path: Path) -> None:
    life = tmp_path / "life"
    (life / "skills").mkdir(parents=True)
    (life / "quests").mkdir(parents=True)
    (life / "quests" / "repair.json").write_text(
        """
{
  "name": "repair",
  "signature": "repair(x)",
  "examples": [{"input": [1], "output": 1}],
  "constraints": {"pure": true, "no_import": true, "time_ms_max": 10},
  "triggers": [{"signal": "noise", "gte": 0.5}],
  "reward": {"mood": "pleasure", "resource_delta": {"food": 1}},
  "penalty": {"mood": "pain"},
  "cooldown": 30,
  "success": {"resource_min": {"energy": 0}}
}
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("SINGULAR_HOME", str(life))
    monkeypatch.setattr(
        "singular.orchestrator.service.capture_signals",
        lambda bus: {"noise": 0.8, "artifact_events": []},
    )

    bus = EventBus()
    service = OrchestratorService(config=OrchestratorConfig(dry_run=True), bus=bus)

    service.tick()  # VEILLE -> trigger
    service.tick()  # ACTION -> resolve

    quests_path = life / "mem" / "quests_state.json"
    assert quests_path.exists()
    payload = quests_path.read_text(encoding="utf-8")
    assert '"repair"' in payload
    assert '"success"' in payload


def test_orchestrator_action_executes_skill_runtime(monkeypatch, tmp_path: Path) -> None:
    life = tmp_path / "life"
    (life / "skills").mkdir(parents=True)
    (life / "mem").mkdir(parents=True)
    (life / "skills" / "a.py").write_text("result = 1", encoding="utf-8")

    monkeypatch.setenv("SINGULAR_HOME", str(life))

    from singular.skills.runtime import SkillExecutionResult

    calls: list[tuple[object, object]] = []

    def _fake_execute(task, context):
        calls.append((task, context))
        return SkillExecutionResult(skill="a", status="succeeded", score=0.9)

    monkeypatch.setattr("singular.orchestrator.service.run_tick", lambda **kwargs: None)

    bus = EventBus()
    service = OrchestratorService(config=OrchestratorConfig(dry_run=False), bus=bus)
    service.state.current_phase = LifecyclePhase.ACTION.value
    monkeypatch.setattr(service.skill_runtime, "execute_best_skill", _fake_execute)

    service.tick()

    assert calls
    task, context = calls[0]
    assert task["name"] == "orchestrator.action"
    assert context["phase"] == "action"
