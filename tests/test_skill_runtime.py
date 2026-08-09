import json
from pathlib import Path

from singular.events import EventBus
from singular.skills.runtime import SkillRuntime


def test_execute_best_skill_filters_and_scores(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "singular.skills.runtime.sandbox.run", lambda code: {"ok": True}
    )
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


def test_execute_best_skill_rejects_malformed_catalog_annotations(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "singular.skills.runtime.sandbox.run", lambda code: {"ok": True}
    )
    life = tmp_path / "life"
    skills = life / "skills"
    mem = life / "mem"
    skills.mkdir(parents=True)
    mem.mkdir(parents=True)

    (skills / "json_skill.py").write_text(
        '"""Capabilities: json\nInput: json\nOutput: dict\nReliability: very-high\n"""\n\n'
        "def run(context=None):\n    return {'ok': True}\n",
        encoding="utf-8",
    )

    (mem / "skills.json").write_text('{"json_skill": {"risk": 0.0}}', encoding="utf-8")

    runtime = SkillRuntime(skills_dir=skills, mem_dir=mem)
    result = runtime.execute_best_skill(
        task={"name": "json task", "capabilities": ["json"], "input_format": "json"},
        context={"payload": {}},
    )

    assert result.status == "failed"
    assert result.reason == "no_compatible_skill"


def test_execute_best_skill_cautious_strategy_prefers_reliable_skill(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "singular.skills.runtime.sandbox.run", lambda code: {"ok": True}
    )
    life = tmp_path / "life"
    skills = life / "skills"
    mem = life / "mem"
    skills.mkdir(parents=True)
    mem.mkdir(parents=True)

    (skills / "fast.py").write_text(
        "def run(context=None):\n    return {'ok': True}\n", encoding="utf-8"
    )
    (skills / "safe.py").write_text(
        "def run(context=None):\n    return {'ok': True}\n", encoding="utf-8"
    )
    (mem / "skills.json").write_text(
        """
{
  "fast": {
    "capabilities": ["assist"],
    "risk": 0.8,
    "metrics": {"usage_count": 20, "average_gain": 2.0, "average_cost": 0.1, "failure_count": 8}
  },
  "safe": {
    "capabilities": ["assist"],
    "risk": 0.1,
    "metrics": {"usage_count": 20, "average_gain": 1.0, "average_cost": 0.4, "failure_count": 1}
  }
}
""".strip(),
        encoding="utf-8",
    )

    runtime = SkillRuntime(skills_dir=skills, mem_dir=mem)
    result = runtime.execute_best_skill(
        task={"name": "assist", "capabilities": ["assist"], "max_risk": 1.0},
        context={"execution_strategy": {"mode": "cautious", "frustration": 0.9}},
    )
    assert result.status == "succeeded"
    assert result.skill == "safe"


def test_execute_best_skill_persists_world_effects(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "singular.skills.runtime.sandbox.run", lambda code: {"ok": True}
    )
    life = tmp_path / "life"
    skills = life / "skills"
    mem = life / "mem"
    skills.mkdir(parents=True)
    mem.mkdir(parents=True)
    (skills / "good.py").write_text(
        "def run(context=None):\n    return {'ok': True}\n", encoding="utf-8"
    )
    (mem / "skills.json").write_text(
        '{"good": {"capabilities": ["assist"], "risk": 0.1}}', encoding="utf-8"
    )

    runtime = SkillRuntime(skills_dir=skills, mem_dir=mem)
    result = runtime.execute_best_skill(
        task={"name": "assist", "capabilities": ["assist"]},
        context={},
    )

    assert result.status == "succeeded"
    effects = json.loads((mem / "world_effects.json").read_text(encoding="utf-8"))
    assert effects["last_effect_count"] == 1
    assert effects["cumulative_effect"]["health_delta"] > 0


def test_runtime_rejects_available_skill_after_source_mutation(tmp_path: Path) -> None:
    import hashlib

    skills = tmp_path / "skills"
    mem = tmp_path / "mem"
    skills.mkdir()
    mem.mkdir()
    source = "def run(context=None):\n    return {'covered': True}\n"
    path = skills / "gap.py"
    path.write_text(source, encoding="utf-8")
    (mem / "skills.json").write_text(
        json.dumps(
            {
                "gap": {
                    "capabilities": ["gap"],
                    "publication_state": "available",
                    "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                }
            }
        ),
        encoding="utf-8",
    )
    path.write_text("def run(context=None):\n    return {'covered': False}\n")

    result = SkillRuntime(skills_dir=skills, mem_dir=mem).execute_best_skill(
        {"capabilities": ["gap"]}, {}
    )

    assert result.reason == "no_compatible_skill"


def _exploration_runtime(root: Path, monkeypatch, *, failing: set[str] | None = None):
    skills = root / "skills"
    mem = root / "mem"
    skills.mkdir(parents=True)
    mem.mkdir(parents=True)
    states = {}
    for index, name in enumerate(("reliable", "novel_a", "novel_b")):
        (skills / f"{name}.py").write_text(
            f"def run(context=None):\n    return {{'skill': '{name}'}}\n",
            encoding="utf-8",
        )
        states[name] = {
            "capabilities": ["choose"],
            "risk": 0.05 if name == "reliable" else 0.2,
            "metrics": {
                "usage_count": 20 if name == "reliable" else index,
                "average_gain": 1.5 if name == "reliable" else 0.4,
                "average_cost": 0.1,
                "failure_count": 0,
            },
        }
    (mem / "skills.json").write_text(json.dumps(states), encoding="utf-8")

    def run(source: str):
        selected = next(name for name in states if f"'skill': '{name}'" in source)
        if selected in (failing or set()):
            raise RuntimeError("deterministic failure")
        return {"skill": selected}

    monkeypatch.setattr("singular.skills.runtime.sandbox.run", run)
    return SkillRuntime(skills_dir=skills, mem_dir=mem), mem


def test_high_curiosity_diversifies_compatible_strategies(
    monkeypatch, tmp_path: Path
) -> None:
    runtime, mem = _exploration_runtime(tmp_path, monkeypatch)
    chosen = [
        runtime.execute_best_skill(
            {"name": "choose", "capabilities": ["choose"], "max_risk": 0.3},
            {
                "execution_strategy": {
                    "mode": "exploratory",
                    "curiosity": 1,
                    "energy": 1,
                    "seed": 7,
                }
            },
        ).skill
        for _ in range(3)
    ]

    assert len(set(chosen)) > 1
    decisions = [
        json.loads(line)
        for line in (mem / "skill_selection.jsonl").read_text().splitlines()
    ]
    assert any(item.get("policy") == "exploration" for item in decisions)


def test_high_risk_pressure_keeps_reliable_strategy(
    monkeypatch, tmp_path: Path
) -> None:
    runtime, _ = _exploration_runtime(tmp_path, monkeypatch)
    result = runtime.execute_best_skill(
        {"name": "choose", "capabilities": ["choose"]},
        {
            "execution_strategy": {
                "mode": "exploratory",
                "curiosity": 1,
                "risk": 1,
                "seed": 2,
            }
        },
    )
    assert result.skill == "reliable"


def test_repeated_exploration_failures_restore_reliable_strategy(
    monkeypatch, tmp_path: Path
) -> None:
    runtime, _ = _exploration_runtime(
        tmp_path, monkeypatch, failing={"novel_a", "novel_b"}
    )
    context = {
        "execution_strategy": {
            "mode": "exploratory",
            "curiosity": 1,
            "energy": 1,
            "seed": 4,
        }
    }
    first = runtime.execute_best_skill(
        {"name": "choose", "capabilities": ["choose"]}, context
    )
    second = runtime.execute_best_skill(
        {"name": "choose", "capabilities": ["choose"]}, context
    )
    cautious = runtime.execute_best_skill(
        {"name": "choose", "capabilities": ["choose"]},
        {
            "execution_strategy": {
                "mode": "cautious",
                "curiosity": 1,
                "frustration": 1,
                "seed": 4,
            }
        },
    )
    assert first.status == second.status == "failed"
    assert cautious.skill == "reliable"
    assert cautious.status == "succeeded"


def test_fixed_seed_reproduces_exploration_sequence(
    monkeypatch, tmp_path: Path
) -> None:
    sequences = []
    for name in ("one", "two"):
        runtime, _ = _exploration_runtime(tmp_path / name, monkeypatch)
        context = {
            "execution_strategy": {
                "mode": "exploratory",
                "curiosity": 0.6,
                "energy": 1,
                "seed": 91,
            }
        }
        sequences.append(
            [
                runtime.execute_best_skill(
                    {"name": "choose", "capabilities": ["choose"]}, context
                ).skill
                for _ in range(5)
            ]
        )
    assert sequences[0] == sequences[1]
