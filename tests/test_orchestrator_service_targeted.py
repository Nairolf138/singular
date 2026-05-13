from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from singular.events import EventBus, HELP_REQUESTED
from singular.orchestrator import service as orchestrator_service
from singular.orchestrator.service import LifecyclePhase, OrchestratorConfig, OrchestratorService, SchedulerConfig
from singular.skills.runtime import SkillExecutionResult


def _service(root, *, bus=None, dry_run=True, **config_kwargs) -> OrchestratorService:
    return OrchestratorService(
        config=OrchestratorConfig(
            scheduler=SchedulerConfig(veille_seconds=0.01, action_seconds=0.01, introspection_seconds=0.01, sommeil_seconds=0.01),
            poll_interval_seconds=0.01,
            tick_budget_seconds=0.05,
            mutation_window_seconds=0.05,
            dry_run=dry_run,
            **config_kwargs,
        ),
        bus=bus or EventBus(),
        base_dir=root,
    )


def test_runtime_adaptation_prudent_mode_and_skip_action(temp_life) -> None:
    service = _service(temp_life["root"])
    service._latest_signals = {
        "host_metrics": {
            "cpu_percent": 99.0,
            "ram_used_percent": 99.0,
            "host_temperature_c": 999.0,
        }
    }

    adaptation = service._compute_runtime_adaptation()

    assert adaptation["enforce_prudent_mode"] is True
    assert adaptation["skip_action_tick"] is True
    assert "cpu_high_critical" in adaptation["rule_triggers"]
    assert "thermal_critical_sleep" in adaptation["rule_triggers"]


def test_startup_stop_signal_is_honored_without_tick(temp_life, monkeypatch) -> None:
    service = _service(temp_life["root"])
    service.stop_signal_path.write_text(
        json.dumps({"reason": "test", "requested_at": datetime.now(timezone.utc).isoformat()}),
        encoding="utf-8",
    )
    called = {"tick": 0}
    monkeypatch.setattr(service, "tick", lambda: called.__setitem__("tick", called["tick"] + 1))

    service.run_forever()

    assert called["tick"] == 0
    assert service._running is False


def test_transient_tick_errors_backoff_then_continue(temp_life, monkeypatch) -> None:
    service = _service(temp_life["root"], max_consecutive_tick_failures=3, tick_failure_backoff_seconds=0.01)
    calls = {"tick": 0, "sleep": 0}

    def flaky_tick():
        calls["tick"] += 1
        if calls["tick"] == 1:
            raise TimeoutError("temporary lock")
        service._running = False
        return LifecyclePhase.ACTION

    monkeypatch.setattr(service, "tick", flaky_tick)
    monkeypatch.setattr(orchestrator_service.time, "sleep", lambda _seconds: calls.__setitem__("sleep", calls["sleep"] + 1))

    service.run_forever()

    assert calls["tick"] == 2
    assert calls["sleep"] >= 1


def test_veille_phase_triggers_quests(temp_life, monkeypatch) -> None:
    service = _service(temp_life["root"])
    monkeypatch.setattr(orchestrator_service, "capture_signals", lambda bus=None: {"novelty": 1.0})
    triggered: list[dict[str, object]] = []

    def fake_evaluate(signals):
        triggered.append(dict(signals))
        return [{"quest_id": "q1", "status": "started"}]

    service.quest_runtime.evaluate_triggers = fake_evaluate

    service._run_phase(LifecyclePhase.VEILLE)

    assert triggered == [{"novelty": 1.0}]
    assert service.state.last_events[-1]["details"]["quests_triggered"][0]["quest_id"] == "q1"


@dataclass
class _RoutineSpec:
    id: str
    prompt: str
    priority: int


def test_action_phase_orchestrates_skill_routines_and_life_tick(temp_life, monkeypatch) -> None:
    service = _service(temp_life["root"], dry_run=False)
    service._latest_signals = {"host_metrics": {"cpu_percent": 10.0, "ram_used_percent": 10.0, "host_temperature_c": 20.0}}
    service.routines.specs = [_RoutineSpec("routine", "do", 1)]
    service.goals.derive_execution_strategy = lambda signals: {"mode": "explore"}
    service.goals.adjust_routine_priorities = lambda specs, perception_signals: specs
    service.skill_runtime.execute_best_skill = lambda task, context: SkillExecutionResult("skill", "succeeded", score=1.0)
    service.routines.execute_with_runtime = lambda skill_runtime, base_context, priority_overrides: [{"id": "routine", "status": "done"}]
    service.quest_runtime.settle_active = lambda **kwargs: [{"quest_id": "q1", "status": "settled"}]
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(orchestrator_service, "run_tick", lambda **kwargs: calls.append(kwargs))

    service._run_phase(LifecyclePhase.ACTION)

    assert calls
    assert calls[0]["skills_dirs"] == temp_life["skills_dir"]
    details = service.state.last_events[-1]["details"]
    assert details["skill_execution"]["status"] == "succeeded"
    assert details["routines"] == [{"id": "routine", "status": "done"}]
    assert details["quests"] == [{"quest_id": "q1", "status": "settled"}]


def test_repeated_action_failures_publish_help_request(temp_life) -> None:
    bus = EventBus()
    events = []
    bus.subscribe(HELP_REQUESTED, lambda event: events.append(event))
    service = _service(temp_life["root"], bus=bus, help_request_failure_threshold=2)
    failed = SkillExecutionResult(skill="missing", status="failed", reason="no_compatible_skill")

    service._track_action_failure_and_request_help(task_name="orchestrator.action", skill_execution=failed)
    service._track_action_failure_and_request_help(task_name="orchestrator.action", skill_execution=failed)

    assert len(events) == 1
    assert events[0].payload["task"] == "orchestrator.action"
    assert events[0].payload["attempts"] == 2
