import json
import random
import functools
import sys
from pathlib import Path

import logging
import pytest

root_dir = Path(__file__).resolve().parents[1]
sys.path.append(str(root_dir))
sys.path.append(str(root_dir / "src"))

import life.loop as life_loop
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


def test_log_and_memory_update(tmp_path: Path, monkeypatch):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "foo.py"
    skill.write_text("result = 1", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"

    from singular.runs.logger import RunLogger as RL

    monkeypatch.setattr(
        life_loop, "RunLogger", functools.partial(RL, root=tmp_path / "logs")
    )

    mem_file = tmp_path / "skills.json"

    def fake_update_score(skill: str, score: float) -> None:
        data = json.loads(mem_file.read_text()) if mem_file.exists() else {}
        data[skill] = score
        mem_file.write_text(json.dumps(data))

    monkeypatch.setattr(life_loop, "update_score", fake_update_score)

    run(
        skills_dir,
        checkpoint,
        budget_seconds=0.1,
        rng=random.Random(0),
        run_id="loop",
    )

    assert any((tmp_path / "logs").glob("loop-*.jsonl"))
    assert json.loads(mem_file.read_text())["foo"] > 1


def test_corrupted_checkpoint(tmp_path: Path, caplog):
    ckpt = tmp_path / "ckpt.json"
    ckpt.write_text("{", encoding="utf-8")
    caplog.set_level(logging.WARNING)

    state = load_checkpoint(ckpt)

    assert state == life_loop.Checkpoint()
    assert any(
        "failed to load checkpoint" in record.message for record in caplog.records
    )
