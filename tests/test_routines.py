from pathlib import Path

from singular.routines import RoutinesOrchestrator
from singular.skills.runtime import SkillExecutionResult


def test_routines_generates_due_tasks_and_persists_state(tmp_path: Path) -> None:
    config = tmp_path / "routines.yaml"
    state = tmp_path / "routines_state.json"
    config.write_text(
        """
routines:
  - id: summarize_inbox
    prompt: "Resume inbox"
    interval_minutes: 5
    priority: 80
""".strip(),
        encoding="utf-8",
    )

    orchestrator = RoutinesOrchestrator(config_path=config, state_path=state)
    due = orchestrator.due_tasks()

    assert len(due) == 1
    task = due[0]
    orchestrator.mark_executed(task, success=True, latency_ms=42.0)

    payload = state.read_text(encoding="utf-8")
    assert "summarize_inbox" in payload
    assert "last_run_at" in payload
    assert "next_run_at" in payload


def test_routines_executed_during_action_phase(monkeypatch, tmp_path: Path) -> None:
    life = tmp_path / "life"
    (life / "mem").mkdir(parents=True)
    (life / "skills").mkdir(parents=True)

    routines_config = tmp_path / "routines.yaml"
    routines_config.write_text(
        """
routines:
  - id: answer_human_prompt
    prompt: "Repondre humain"
    interval_minutes: 5
    priority: 90
""".strip(),
        encoding="utf-8",
    )

    calls: list[dict] = []

    class _Runtime:
        def execute_best_skill(self, task, context):
            calls.append({"task": task, "context": context})
            return SkillExecutionResult(skill="a", status="succeeded", score=0.9)

    orchestrator = RoutinesOrchestrator(
        config_path=routines_config,
        state_path=life / "mem" / "routines_state.json",
    )

    outcomes = orchestrator.execute_with_runtime(
        skill_runtime=_Runtime(),
        base_context={"phase": "action"},
    )

    assert outcomes
    assert calls
    assert calls[0]["task"]["name"] == "routine.answer_human_prompt"
    assert (life / "mem" / "routines_state.json").exists()
