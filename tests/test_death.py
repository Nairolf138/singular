import json
import ast
import random
from pathlib import Path

import functools

import life.loop as life_loop
from life.loop import run
from life.death import DeathMonitor


def _inc_operator(tree: ast.AST, rng=None) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            node.value += 1
            break
    return tree


def _dec_operator(tree: ast.AST, rng=None) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            node.value -= 1
            break
    return tree


def _setup(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "foo.py"
    skill.write_text("result = 1", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"
    return skills_dir, checkpoint


def _patch_logger(monkeypatch, tmp_path: Path):
    from singular.runs.logger import RunLogger as RL

    monkeypatch.setattr(
        life_loop, "RunLogger", functools.partial(RL, root=tmp_path / "logs")
    )


def _patch_memory(monkeypatch, tmp_path: Path):
    import singular.runs.logger as logger_mod
    import json

    episodic = tmp_path / "mem" / "episodic.jsonl"

    def fake_add_episode(episode, path=episodic):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(episode) + "\n")

    monkeypatch.setattr(logger_mod, "add_episode", fake_add_episode)
    monkeypatch.setattr(life_loop, "update_score", lambda *a, **k: None)
    monkeypatch.setattr(
        life_loop.Psyche, "load_state", staticmethod(lambda: life_loop.Psyche())
    )
    return episodic


def _read_log(tmp_path: Path):
    logs = list((tmp_path / "logs").glob("loop-*.jsonl"))
    assert logs
    return [json.loads(line) for line in logs[0].read_text().splitlines()]


def test_death_by_age(tmp_path: Path, monkeypatch):
    skills_dir, ckpt = _setup(tmp_path)
    _patch_logger(monkeypatch, tmp_path)
    episodic = _patch_memory(monkeypatch, tmp_path)

    monitor = DeathMonitor(max_age=2, max_failures=99, min_trait=0.0)

    state = run(
        skills_dir,
        ckpt,
        budget_seconds=10.0,
        rng=random.Random(0),
        run_id="loop",
        operators={"inc": _inc_operator},
        mortality=monitor,
    )

    assert state.iteration == 2
    log = _read_log(tmp_path)
    assert log[-1]["event"] == "death"
    episodes = episodic.read_text().splitlines()
    assert any(json.loads(line)["event"] == "death" for line in episodes)


def test_death_by_failures(tmp_path: Path, monkeypatch):
    skills_dir, ckpt = _setup(tmp_path)
    _patch_logger(monkeypatch, tmp_path)
    _patch_memory(monkeypatch, tmp_path)

    monitor = DeathMonitor(max_age=99, max_failures=2)

    state = run(
        skills_dir,
        ckpt,
        budget_seconds=1.0,
        rng=random.Random(0),
        run_id="loop",
        operators={"dec": _dec_operator},
        mortality=monitor,
    )

    assert state.iteration == 2
    log = _read_log(tmp_path)
    assert log[-1]["event"] == "death"


def test_death_by_traits(tmp_path: Path, monkeypatch):
    skills_dir, ckpt = _setup(tmp_path)
    _patch_logger(monkeypatch, tmp_path)
    _patch_memory(monkeypatch, tmp_path)

    class LowPsyche:
        curiosity = 0.0
        patience = 0.0
        playfulness = 0.0
        last_mood = None

        def mutation_policy(self):
            return "explore"

        def process_run_record(self, record):
            pass

        def save_state(self):
            pass

    monkeypatch.setattr(
        life_loop.Psyche, "load_state", staticmethod(lambda: LowPsyche())
    )

    monitor = DeathMonitor(max_age=99, max_failures=99, min_trait=0.1)

    state = run(
        skills_dir,
        ckpt,
        budget_seconds=1.0,
        rng=random.Random(0),
        run_id="loop",
        operators={"inc": _inc_operator},
        mortality=monitor,
    )

    assert state.iteration == 1
    log = _read_log(tmp_path)
    assert log[-1]["event"] == "death"
