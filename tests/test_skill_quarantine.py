from __future__ import annotations

import ast
import functools
import json
import random
from pathlib import Path

import singular.life.loop as life_loop
from singular.runs.logger import RunLogger as BaseRunLogger


def _noop_operator(tree: ast.AST, rng=None) -> ast.AST:
    return tree


def test_loop_quarantines_skill_after_repeated_sandbox_failures(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))
    monkeypatch.setattr(
        life_loop, "RunLogger", functools.partial(BaseRunLogger, root=tmp_path / "runs")
    )
    monkeypatch.setattr(
        life_loop.Psyche, "load_state", staticmethod(lambda: life_loop.Psyche())
    )
    monkeypatch.setattr(life_loop, "SKILL_SANDBOX_QUARANTINE_THRESHOLD", 2)
    monkeypatch.setattr(life_loop, "SKILL_SANDBOX_QUARANTINE_HOURS", 1)

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / "unsafe.py").write_text("import os\nresult = 1\n", encoding="utf-8")

    life_loop.run(
        skills_dirs=skills_dir,
        checkpoint_path=tmp_path / "checkpoint.json",
        budget_seconds=10.0,
        rng=random.Random(0),
        run_id="quarantine",
        operators={"noop": _noop_operator},
        max_iterations=2,
    )

    skills = json.loads((tmp_path / "mem" / "skills.json").read_text(encoding="utf-8"))
    lifecycle = skills["unsafe"]["lifecycle"]
    assert lifecycle["state"] == "temporarily_disabled"
    assert lifecycle["state_reason"] == "consecutive_sandbox_failures"
    assert lifecycle["disabled_until"] is not None

    events = [
        json.loads(line)
        for line in (tmp_path / "runs" / "quarantine" / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    quarantines = [
        event for event in events if event.get("event_type") == "skill.quarantined"
    ]
    assert quarantines
    payload = quarantines[-1]["payload"]
    assert payload["skill"] == "unsafe"
    assert payload["reason"] == "consecutive_sandbox_failures"
    assert payload["sandbox_error_type"] == "sandbox_error"
    assert payload["disabled_until"] == lifecycle["disabled_until"]
    assert payload["attempts"] == 2
