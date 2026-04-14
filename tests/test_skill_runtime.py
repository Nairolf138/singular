from pathlib import Path

from singular.events import EventBus
from singular.skills.runtime import SkillRuntime


def test_execute_best_skill_filters_and_scores(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("singular.skills.runtime.sandbox.run", lambda code: {"ok": True})
    life = tmp_path / "life"
    skills = life / "skills"
    mem = life / "mem"
    skills.mkdir(parents=True)
    mem.mkdir(parents=True)

    (skills / "good.py").write_text(
        "def run(context=None):\n    return {'ok': True, 'name': 'good'}\n",
        encoding="utf-8",
    )
    (skills / "bad.py").write_text(
        "def run(context=None):\n    return {'ok': True, 'name': 'bad'}\n",
        encoding="utf-8",
    )

    (mem / "skills.json").write_text(
        """
{
  "good": {
    "capabilities": ["math"],
    "risk": 0.1,
    "metrics": {
      "usage_count": 10,
      "average_gain": 2.0,
      "average_cost": 0.2,
      "failure_count": 1
    }
  },
  "bad": {
    "capabilities": ["math"],
    "risk": 0.8,
    "metrics": {
      "usage_count": 10,
      "average_gain": 0.1,
      "average_cost": 2.0,
      "failure_count": 8
    }
  }
}
""".strip(),
        encoding="utf-8",
    )

    events: list[str] = []
    bus = EventBus()
    bus.subscribe("skill.execution.started", lambda e: events.append(e.event_type))
    bus.subscribe("skill.execution.succeeded", lambda e: events.append(e.event_type))

    runtime = SkillRuntime(skills_dir=skills, mem_dir=mem, bus=bus)
    result = runtime.execute_best_skill(
        task={"name": "solve", "capabilities": ["math"], "max_risk": 0.5},
        context={"x": 1},
    )

    assert result.status == "succeeded"
    assert result.skill == "good"
    assert events == ["skill.execution.started", "skill.execution.succeeded"]


def test_execute_best_skill_emits_failed_when_none(tmp_path: Path) -> None:
    life = tmp_path / "life"
    skills = life / "skills"
    mem = life / "mem"
    skills.mkdir(parents=True)
    mem.mkdir(parents=True)
    (mem / "skills.json").write_text("{}", encoding="utf-8")

    failed_payloads: list[dict] = []
    bus = EventBus()
    bus.subscribe("skill.execution.failed", lambda e: failed_payloads.append(e.payload))

    runtime = SkillRuntime(skills_dir=skills, mem_dir=mem, bus=bus)
    result = runtime.execute_best_skill(
        task={"name": "empty", "capabilities": ["missing"]},
        context={},
    )

    assert result.status == "failed"
    assert result.reason == "no_compatible_skill"
    assert failed_payloads[-1]["reason"] == "no_compatible_skill"
