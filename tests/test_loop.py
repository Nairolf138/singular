import json
import random
from pathlib import Path

import pytest

from life.loop import run, load_checkpoint


def _read_result(path: Path) -> int:
    return int(path.read_text(encoding="utf-8").split("=")[1])


def test_mutation_persistence(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "foo.py"
    skill.write_text("result = 1", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"

    run(skills_dir, checkpoint, budget_seconds=0.1, rng=random.Random(0))

    assert _read_result(skill) > 1
    state = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert state["iteration"] >= 1


def test_resume_from_checkpoint(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "foo.py"
    skill.write_text("result = 1", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"
    rng = random.Random(0)

    run(skills_dir, checkpoint, budget_seconds=0.1, rng=rng)
    first_val = _read_result(skill)
    first_iter = load_checkpoint(checkpoint).iteration

    run(skills_dir, checkpoint, budget_seconds=0.1, rng=rng)
    second_val = _read_result(skill)
    second_iter = load_checkpoint(checkpoint).iteration

    assert second_iter > first_iter
    assert second_val > first_val
