from pathlib import Path
from datetime import timedelta
import json
import logging

import pytest

from singular.events import EventBus
from singular.orchestrator.service import (
    LifecyclePhase,
    OrchestratorConfig,
    OrchestratorService,
    SchedulerConfig,
)
from singular.routines import RoutinesOrchestrator
from singular.skills.runtime import SkillExecutionResult


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
  "success": {"resource_min": {"energy": 0}},
  "origin": "intrinsic"
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
    assert '"origin": "intrinsic"' in payload


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


def test_orchestrator_action_passes_world_state_to_tick(monkeypatch, tmp_path: Path) -> None:
    life = tmp_path / "life"
    (life / "skills").mkdir(parents=True)
    (life / "mem").mkdir(parents=True)
    (life / "skills" / "a.py").write_text("result = 1", encoding="utf-8")
    monkeypatch.setenv("SINGULAR_HOME", str(life))

    captured: dict[str, object] = {}

    def _fake_run_tick(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("singular.orchestrator.service.run_tick", _fake_run_tick)
    service = OrchestratorService(config=OrchestratorConfig(dry_run=False), bus=EventBus())
    service.state.current_phase = LifecyclePhase.ACTION.value
    monkeypatch.setattr(
        service.skill_runtime,
        "execute_best_skill",
        lambda task, context: SkillExecutionResult(skill="a", status="succeeded", score=1.0),
    )

    service.tick()

    assert captured["world"] is service.world_state


def test_orchestrator_requests_help_after_failure_streak(monkeypatch, tmp_path: Path) -> None:
    life = tmp_path / "life"
    (life / "skills").mkdir(parents=True)
    (life / "mem").mkdir(parents=True)
    (life / "skills" / "a.py").write_text("result = 1", encoding="utf-8")
    monkeypatch.setenv("SINGULAR_HOME", str(life))
    monkeypatch.setattr("singular.orchestrator.service.run_tick", lambda **kwargs: None)

    events: list[dict[str, object]] = []
    bus = EventBus()
    bus.subscribe("help.requested", lambda event: events.append(event.payload))
    service = OrchestratorService(
        config=OrchestratorConfig(dry_run=False, help_request_failure_threshold=2),
        bus=bus,
    )
    service.state.current_phase = LifecyclePhase.ACTION.value

    def _fail_execute(task, context):
        return SkillExecutionResult(
            skill="a",
            status="failed",
            score=0.1,
            reason="sandbox failure",
        )

    monkeypatch.setattr(service.skill_runtime, "execute_best_skill", _fail_execute)
    service.tick()
    service.state.current_phase = LifecyclePhase.ACTION.value
    service.tick()

    assert len(events) == 1
    assert events[0]["task"] == "orchestrator.action"
    assert events[0]["attempts"] == 2


def test_orchestrator_repeated_negative_feedback_reprioritizes_action_routines(monkeypatch, tmp_path: Path) -> None:
    life = tmp_path / "life"
    (life / "skills").mkdir(parents=True)
    (life / "mem").mkdir(parents=True)
    (life / "skills" / "a.py").write_text("result = 1", encoding="utf-8")
    routines_config = tmp_path / "routines.yaml"
    routines_config.write_text(
        """
routines:
  - id: deep_research
    prompt: "explore roadmap"
    interval_minutes: 5
    priority: 90
  - id: user_support
    prompt: "help user quickly"
    interval_minutes: 5
    priority: 40
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("SINGULAR_HOME", str(life))
    monkeypatch.setattr("singular.orchestrator.service.run_tick", lambda **kwargs: None)
    monkeypatch.setattr(
        "singular.orchestrator.service.capture_signals",
        lambda bus: {
            "episode_memory": {
                "structured_feedback": {
                    "frustration": 0.9,
                    "satisfaction": 0.1,
                    "urgency": 0.8,
                    "theme": "support",
                },
                "negative_feedback_streak": 3,
            }
        },
    )

    calls: list[dict[str, object]] = []

    def _fake_execute(task, context):
        calls.append({"task": task, "context": context})
        return SkillExecutionResult(skill="a", status="succeeded", score=0.9)

    service = OrchestratorService(config=OrchestratorConfig(dry_run=False), bus=EventBus())
    service.routines = RoutinesOrchestrator(
        config_path=routines_config,
        state_path=life / "mem" / "routines_state.json",
    )
    monkeypatch.setattr(service.skill_runtime, "execute_best_skill", _fake_execute)

    service.tick()  # VEILLE
    service.tick()  # ACTION

    routine_tasks = [entry["task"] for entry in calls if str(entry["task"].get("name", "")).startswith("routine.")]
    assert routine_tasks
    assert routine_tasks[0]["name"] == "routine.user_support"
    assert routine_tasks[0]["priority"] > 90


def test_orchestrator_run_forever_consumes_stale_startup_stop_signal(
    monkeypatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    life = tmp_path / "life"
    (life / "skills").mkdir(parents=True)
    (life / "mem").mkdir(parents=True)
    monkeypatch.setenv("SINGULAR_HOME", str(life))

    service = OrchestratorService(config=OrchestratorConfig(dry_run=True), bus=EventBus())
    stale_requested_at = (service._started_at - timedelta(minutes=5)).isoformat()
    service.stop_signal_path.write_text(
        json.dumps(
            {
                "stop": True,
                "reason": "life_extinction_detected",
                "requested_at": stale_requested_at,
            }
        ),
        encoding="utf-8",
    )

    called = {"tick": 0}
    def _fake_tick() -> LifecyclePhase:
        called["tick"] += 1
        service._running = False
        return LifecyclePhase.ACTION

    monkeypatch.setattr(service, "tick", _fake_tick)
    monkeypatch.setattr(service, "_external_stimulus_detected", lambda: True)
    caplog.set_level(logging.INFO)

    service.run_forever()

    assert called["tick"] == 1
    assert not service.stop_signal_path.exists()
    archived = sorted((life / "mem").glob("orchestrator.stop.consumed.*.json"))
    assert archived
    assert "startup_stop_signal_detected" in caplog.text
    assert "startup_stop_signal_consumed" in caplog.text


def test_orchestrator_run_forever_honors_runtime_stop_signal(monkeypatch, tmp_path: Path) -> None:
    life = tmp_path / "life"
    (life / "skills").mkdir(parents=True)
    (life / "mem").mkdir(parents=True)
    monkeypatch.setenv("SINGULAR_HOME", str(life))

    service = OrchestratorService(config=OrchestratorConfig(dry_run=True), bus=EventBus())
    called = {"tick": 0}

    def _fake_tick() -> LifecyclePhase:
        called["tick"] += 1
        service.stop_signal_path.write_text('{"stop": true}', encoding="utf-8")
        return LifecyclePhase.ACTION

    monkeypatch.setattr(service, "tick", _fake_tick)
    monkeypatch.setattr(service, "_external_stimulus_detected", lambda: True)

    service.run_forever()

    assert called["tick"] == 1


def test_orchestrator_run_forever_recovers_from_transient_tick_failure(
    monkeypatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    life = tmp_path / "life"
    (life / "skills").mkdir(parents=True)
    (life / "mem").mkdir(parents=True)
    monkeypatch.setenv("SINGULAR_HOME", str(life))

    service = OrchestratorService(config=OrchestratorConfig(dry_run=True), bus=EventBus())
    calls = {"tick": 0}
    sleep_calls: list[float] = []

    def _fake_tick() -> LifecyclePhase:
        calls["tick"] += 1
        if calls["tick"] == 1:
            raise PermissionError("temporary permission glitch")
        service._running = False
        return LifecyclePhase.ACTION

    monkeypatch.setattr(service, "tick", _fake_tick)
    monkeypatch.setattr(service, "_external_stimulus_detected", lambda: True)
    monkeypatch.setattr("singular.orchestrator.service.time.sleep", lambda seconds: sleep_calls.append(seconds))
    caplog.set_level(logging.WARNING)

    service.run_forever()

    assert calls["tick"] == 2
    assert sleep_calls
    assert "phase=" in caplog.text
    assert str(service.state_path) in caplog.text


def test_orchestrator_run_forever_raises_after_transient_tick_failure_threshold(
    monkeypatch,
    tmp_path: Path,
) -> None:
    life = tmp_path / "life"
    (life / "skills").mkdir(parents=True)
    (life / "mem").mkdir(parents=True)
    monkeypatch.setenv("SINGULAR_HOME", str(life))

    service = OrchestratorService(
        config=OrchestratorConfig(
            dry_run=True,
            max_consecutive_tick_failures=2,
            tick_failure_backoff_seconds=0.01,
        ),
        bus=EventBus(),
    )
    monkeypatch.setattr(service, "tick", lambda: (_ for _ in ()).throw(PermissionError("still locked")))
    monkeypatch.setattr("singular.orchestrator.service.time.sleep", lambda seconds: None)

    with pytest.raises(PermissionError):
        service.run_forever()


def test_orchestrator_introspection_refreshes_self_narrative(monkeypatch, tmp_path: Path) -> None:
    life = tmp_path / "life"
    (life / "skills").mkdir(parents=True)
    (life / "mem").mkdir(parents=True)
    (life / "runs").mkdir(parents=True)
    (life / "mem" / "episodic.jsonl").write_text(
        '{"event":"quest","status":"success"}\n{"event":"repair","status":"failure"}\n',
        encoding="utf-8",
    )
    (life / "runs" / "run-1.jsonl").write_text('{"event":"mutation.applied"}\n', encoding="utf-8")
    monkeypatch.setenv("SINGULAR_HOME", str(life))

    events: list[dict[str, object]] = []
    bus = EventBus()
    bus.subscribe("self_narrative.updated", lambda event: events.append(event.payload))
    service = OrchestratorService(config=OrchestratorConfig(dry_run=True), bus=bus)
    service.state.current_phase = LifecyclePhase.INTROSPECTION.value

    service.tick()

    path = life / "mem" / "self_narrative.json"
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["current_heading"]
    assert events
    assert events[-1]["event_type"] == "self_narrative.updated"
    assert any(
        isinstance(item, dict)
        and isinstance(item.get("details"), dict)
        and item["details"].get("event_type") == "self_narrative.updated"
        for item in service.state.last_events
    )


def test_orchestrator_introspection_frequency_uses_introspection_ticks(monkeypatch, tmp_path: Path) -> None:
    life = tmp_path / "life"
    (life / "skills").mkdir(parents=True)
    (life / "mem").mkdir(parents=True)
    monkeypatch.setenv("SINGULAR_HOME", str(life))

    events: list[dict[str, object]] = []
    bus = EventBus()
    bus.subscribe("self_narrative.updated", lambda event: events.append(event.payload))
    service = OrchestratorService(
        config=OrchestratorConfig(dry_run=True, introspection_frequency_ticks=2),
        bus=bus,
    )
    service.state.current_phase = LifecyclePhase.INTROSPECTION.value
    service.tick()
    assert not events
    service.state.current_phase = LifecyclePhase.INTROSPECTION.value
    service.tick()
    assert len(events) == 1
