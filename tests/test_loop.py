import json
import random
import functools
import sys
from pathlib import Path

import ast

import logging

root_dir = Path(__file__).resolve().parents[1]
sys.path.append(str(root_dir))
sys.path.append(str(root_dir / "src"))

import life.loop as life_loop  # noqa: E402
from life.loop import run, load_checkpoint  # noqa: E402
from singular.resource_manager import ResourceManager  # noqa: E402


def _inc_operator(tree: ast.AST, rng=None) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            node.value += 1
            break
    return tree


def _read_result(path: Path) -> int:
    return int(path.read_text(encoding="utf-8").split("=")[1])


def test_mutation_persistence(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "foo.py"
    skill.write_text("result = 1", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"

    run(
        skills_dir,
        checkpoint,
        budget_seconds=0.1,
        rng=random.Random(0),
        operators={"dec": _dec_operator},
    )

    assert _read_result(skill) < 1
    state = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert state["iteration"] >= 1


def test_resume_from_checkpoint(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "foo.py"
    skill.write_text("result = 1", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"
    rng = random.Random(0)

    run(
        skills_dir,
        checkpoint,
        budget_seconds=0.1,
        rng=rng,
        operators={"dec": _dec_operator},
    )
    first_val = _read_result(skill)
    first_iter = load_checkpoint(checkpoint).iteration

    run(
        skills_dir,
        checkpoint,
        budget_seconds=0.1,
        rng=rng,
        operators={"dec": _dec_operator},
    )
    second_val = _read_result(skill)
    second_iter = load_checkpoint(checkpoint).iteration

    assert second_iter > first_iter
    assert second_val <= first_val


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
        data[skill] = {"score": score}
        mem_file.write_text(json.dumps(data))

    monkeypatch.setattr(life_loop, "update_score", fake_update_score)

    run(
        skills_dir,
        checkpoint,
        budget_seconds=0.1,
        rng=random.Random(0),
        run_id="loop",
        operators={"dec": _dec_operator},
    )

    assert any((tmp_path / "logs").glob("loop-*.jsonl"))
    assert json.loads(mem_file.read_text())["foo"]["score"] < 1


def test_mood_style_logged(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))

    class DummyPsyche:
        last_mood = "colere"

        def process_run_record(self, record):
            pass

    from singular.runs.logger import RunLogger, mood_styles

    logger = RunLogger("mood", root=tmp_path / "logs", psyche=DummyPsyche())
    logger.log("skill", "op", "diff", True, 0, 0, 0, 0)
    logger.close()

    episodes = (tmp_path / "mem" / "episodic.jsonl").read_text().splitlines()
    rec = json.loads(episodes[-1])
    assert rec["mood"] == mood_styles["colere"]("colere")


def test_corrupted_checkpoint(tmp_path: Path, caplog):
    ckpt = tmp_path / "ckpt.json"
    ckpt.write_text("{", encoding="utf-8")
    caplog.set_level(logging.WARNING)

    state = load_checkpoint(ckpt)

    assert state == life_loop.Checkpoint()
    assert any(
        "failed to load checkpoint" in record.message for record in caplog.records
    )


def _inc2_operator(tree: ast.AST, rng=None) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            node.value += 2
            break
    return tree


def _dec_operator(tree: ast.AST, rng=None) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            node.value -= 1
            break
    return tree


def test_multi_operator_selection(tmp_path: Path, monkeypatch):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "foo.py"
    skill.write_text("result = 1", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"

    from singular.runs.logger import RunLogger as RL

    monkeypatch.setattr(
        life_loop, "RunLogger", functools.partial(RL, root=tmp_path / "logs")
    )

    class DummyPsyche:
        last_mood = None

        def mutation_policy(self):
            return "analyze"

        def process_run_record(self, record):
            pass

        def save_state(self):
            pass

    monkeypatch.setattr(
        life_loop.Psyche, "load_state", staticmethod(lambda: DummyPsyche())
    )

    operators = {"op1": _inc_operator, "op2": _inc2_operator}

    run(
        skills_dir,
        checkpoint,
        budget_seconds=0.2,
        rng=random.Random(0),
        run_id="loop",
        operators=operators,
    )

    log_files = list((tmp_path / "logs").glob("loop-*.jsonl"))
    assert log_files
    entries = [json.loads(line) for line in log_files[0].read_text().splitlines()]
    used = {e["op"] for e in entries}
    assert {"op1", "op2"} <= used


def test_bandit_persistence_and_exploitation(tmp_path: Path, monkeypatch):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "foo.py"
    skill.write_text("result = 1", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"

    from singular.runs.logger import RunLogger as RL

    monkeypatch.setattr(
        life_loop, "RunLogger", functools.partial(RL, root=tmp_path / "logs")
    )

    class PsyAnalyze:
        def mutation_policy(self):
            return "analyze"

        def process_run_record(self, record):
            pass

        def save_state(self):
            pass

    class PsyExploit:
        def mutation_policy(self):
            return "exploit"

        def process_run_record(self, record):
            pass

        def save_state(self):
            pass

    operators = {"inc": _inc_operator, "dec": _dec_operator}

    monkeypatch.setattr(
        life_loop.Psyche, "load_state", staticmethod(lambda: PsyAnalyze())
    )

    run(
        skills_dir,
        checkpoint,
        budget_seconds=0.2,
        rng=random.Random(0),
        run_id="loop1",
        operators=operators,
        mortality=life_loop.DeathMonitor(max_failures=100),
    )

    first_stats = load_checkpoint(checkpoint).stats
    assert first_stats["inc"]["count"] > 0
    assert first_stats["dec"]["count"] > 0

    monkeypatch.setattr(
        life_loop.Psyche, "load_state", staticmethod(lambda: PsyExploit())
    )

    run(
        skills_dir,
        checkpoint,
        budget_seconds=0.2,
        rng=random.Random(0),
        run_id="loop2",
        operators=operators,
        mortality=life_loop.DeathMonitor(max_failures=100),
    )

    second_stats = load_checkpoint(checkpoint).stats
    assert second_stats["dec"]["count"] > first_stats["dec"]["count"]
    assert second_stats["inc"]["count"] == first_stats["inc"]["count"]


def test_angry_increases_proposals(tmp_path: Path, monkeypatch):
    calls = {"n": 0}

    def fake_propose(zones=None):
        calls["n"] += 1
        return []

    class DummyLogger:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            pass

        def log(self, *a, **k):
            pass

        def log_death(self, *a, **k):
            pass

    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    checkpoint = tmp_path / "ckpt.json"

    psyche = life_loop.Psyche()
    psyche.last_mood = "frustrated"
    psyche.energy = 100.0

    monkeypatch.setattr(life_loop, "propose_mutations", fake_propose)
    monkeypatch.setattr(life_loop.Psyche, "load_state", staticmethod(lambda: psyche))
    monkeypatch.setattr(life_loop, "RunLogger", DummyLogger)

    life_loop.run(
        skill_dir,
        checkpoint,
        budget_seconds=0.0,
        rng=random.Random(0),
        operators={"inc": _inc_operator},
    )

    assert calls["n"] == 2


def test_fatigue_reduces_proposals(tmp_path: Path, monkeypatch):
    calls = {"n": 0}

    def fake_propose(zones=None):
        calls["n"] += 1
        return []

    class DummyLogger:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            pass

        def log(self, *a, **k):
            pass

        def log_death(self, *a, **k):
            pass

    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    checkpoint = tmp_path / "ckpt.json"

    psyche = life_loop.Psyche()
    psyche.last_mood = "frustrated"
    psyche.energy = 20.0

    monkeypatch.setattr(life_loop, "propose_mutations", fake_propose)
    monkeypatch.setattr(life_loop.Psyche, "load_state", staticmethod(lambda: psyche))
    monkeypatch.setattr(life_loop, "RunLogger", DummyLogger)

    life_loop.run(
        skill_dir,
        checkpoint,
        budget_seconds=0.0,
        rng=random.Random(0),
        operators={"inc": _inc_operator},
    )

    assert calls["n"] == 1


def _setup_dummy_psyche(monkeypatch, tmp_path, action):
    """Helper to prepare a ``Psyche`` that always triggers ``action``."""

    class DummyPsyche:
        last_mood = "anxious"

        def mutation_policy(self):
            return "default"

        def process_run_record(self, record):
            pass

        def save_state(self):
            pass

        def consume(self):
            pass

        def irrational_decision(self, rng=None):
            return True

    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))
    monkeypatch.setattr(life_loop.Psyche, "load_state", staticmethod(lambda: DummyPsyche()))

    rng = random.Random(0)
    orig_choice = rng.choice

    def custom_choice(seq):
        if seq == ["refuse", "procrastinate", "absurd"]:
            return action
        return orig_choice(seq)

    rng.choice = custom_choice  # type: ignore[attr-defined]

    from singular.runs.logger import RunLogger as RL

    monkeypatch.setattr(
        life_loop, "RunLogger", functools.partial(RL, root=tmp_path / "logs")
    )
    monkeypatch.setattr(life_loop, "update_score", lambda *a, **k: None)
    monkeypatch.setattr(life_loop, "add_episode", lambda *a, **k: None)
    monkeypatch.setattr(life_loop, "capture_signals", lambda: {})

    return rng


def test_irrational_refusal(tmp_path: Path, monkeypatch):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "foo.py"
    skill.write_text("result = 1", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"

    rng = _setup_dummy_psyche(monkeypatch, tmp_path, "refuse")

    life_loop.run(
        skills_dir,
        checkpoint,
        budget_seconds=0.05,
        rng=rng,
        operators={"dec": _dec_operator},
    )

    assert skill.read_text(encoding="utf-8") == "result = 1"


def test_irrational_procrastination(tmp_path: Path, monkeypatch):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "foo.py"
    skill.write_text("result = 1", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"

    rng = _setup_dummy_psyche(monkeypatch, tmp_path, "procrastinate")

    called = {"sleep": False}

    def fake_sleep(seconds):
        called["sleep"] = seconds

    monkeypatch.setattr(life_loop.time, "sleep", fake_sleep)

    life_loop.run(
        skills_dir,
        checkpoint,
        budget_seconds=0.05,
        rng=rng,
        operators={"dec": _dec_operator},
    )

    assert skill.read_text(encoding="utf-8") == "result = 1"
    assert called["sleep"] == 0.01


def test_irrational_absurd_mutation(tmp_path: Path, monkeypatch):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "foo.py"
    skill.write_text("result = 1", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"

    rng = _setup_dummy_psyche(monkeypatch, tmp_path, "absurd")

    life_loop.run(
        skills_dir,
        checkpoint,
        budget_seconds=0.05,
        rng=rng,
        operators={"dec": _dec_operator},
    )

    assert "absurd" in skill.read_text(encoding="utf-8")


def _dummy_psyche(events):
    class DummyPsyche:
        mutation_rate = 1.0
        energy = 100.0

        def mutation_policy(self):
            return "default"

        def process_run_record(self, record):
            pass

        def save_state(self):
            pass

        def consume(self):
            pass

        def irrational_decision(self, rng=None):
            return False

        def feel(self, mood):
            events.append(mood)

    return DummyPsyche()


def test_energy_debit_and_food_credit(tmp_path: Path, monkeypatch):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "foo.py"
    skill.write_text("result = 1", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"

    events = []
    psyche = _dummy_psyche(events)
    monkeypatch.setattr(life_loop.Psyche, "load_state", staticmethod(lambda: psyche))

    rm = ResourceManager(energy=50.0, food=30.0, warmth=50.0, path=tmp_path / "res.json")

    run(
        skills_dir,
        checkpoint,
        budget_seconds=0.2,
        rng=random.Random(0),
        operators={"dec": _dec_operator},
        resource_manager=rm,
        test_runner=lambda: 3,
    )

    assert rm.energy < 50.0
    assert rm.food >= 3.0
    assert "fatigue" not in events and "anger" not in events


def test_resource_moods_trigger(monkeypatch, tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "foo.py"
    skill.write_text("result = 1", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"

    events = []
    psyche = _dummy_psyche(events)
    monkeypatch.setattr(life_loop.Psyche, "load_state", staticmethod(lambda: psyche))

    rm = ResourceManager(energy=5.0, food=5.0, warmth=50.0, path=tmp_path / "res.json")

    run(
        skills_dir,
        checkpoint,
        budget_seconds=0.2,
        rng=random.Random(0),
        operators={"dec": _dec_operator},
        resource_manager=rm,
        test_runner=lambda: 0,
    )

    assert "fatigue" in events
    assert "anger" in events


def test_warmth_interaction_api(tmp_path: Path):
    rm = ResourceManager(warmth=10.0, path=tmp_path / "res.json")
    rm.simulate_human_interaction(15.0)
    assert rm.warmth == 25.0


def test_auto_post_messages(tmp_path: Path, monkeypatch):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "foo.py"
    skill.write_text("result = 1", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"

    posts: list[str] = []

    def fake_auto_post(channel, message):
        posts.append(message)

    monkeypatch.setattr(life_loop.env_notifications, "auto_post", fake_auto_post)

    run(
        skills_dir,
        checkpoint,
        budget_seconds=0.5,
        rng=random.Random(0),
        operators={"dec": _dec_operator},
    )

    assert posts
