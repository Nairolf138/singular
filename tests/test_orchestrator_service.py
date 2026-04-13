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
