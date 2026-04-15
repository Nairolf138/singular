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

import singular.life.loop as life_loop  # noqa: E402
from singular.life.loop import EcosystemRules, run, load_checkpoint  # noqa: E402
from singular.life.health import detect_health_state  # noqa: E402
from singular.life.test_coevolution import LivingTestPool, TestCandidate  # noqa: E402
from singular.resource_manager import ResourceManager  # noqa: E402
from singular.psyche import Psyche, Mood  # noqa: E402
from singular.governance.policy import MutationGovernancePolicy  # noqa: E402
from singular.life.reproduction import ReproductionDecisionPolicy  # noqa: E402
from singular.events import EventBus  # noqa: E402


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

    calls = {"n": 0}
    original = life_loop.log_mutation

    def wrapped(*a, **k):
        calls["n"] += 1
        return original(*a, **k)

    monkeypatch.setattr(life_loop, "log_mutation", wrapped)

    run(
        skills_dir,
        checkpoint,
        budget_seconds=0.1,
        rng=random.Random(0),
        run_id="loop",
        operators={"dec": _dec_operator},
    )

    assert calls["n"] > 0
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


def test_load_checkpoint_migrates_old_schema(tmp_path: Path):
    ckpt = tmp_path / "ckpt.json"
    ckpt.write_text(json.dumps({"iteration": 7}), encoding="utf-8")

    state = load_checkpoint(ckpt)

    assert state.version == life_loop.CHECKPOINT_VERSION
    assert state.iteration == 7
    assert state.stats == {}
    assert state.health_history == []
    assert state.health_counters == {}


def test_load_checkpoint_ignores_extra_keys(tmp_path: Path):
    ckpt = tmp_path / "ckpt.json"
    ckpt.write_text(
        json.dumps(
            {
                "version": 1,
                "iteration": 3,
                "stats": {},
                "health_history": [],
                "health_counters": {},
                "unexpected": "drop-me",
            }
        ),
        encoding="utf-8",
    )

    state = load_checkpoint(ckpt)

    assert state.version == life_loop.CHECKPOINT_VERSION
    assert state.iteration == 3
    assert not hasattr(state, "unexpected")


def test_reproduction_decision_is_logged_with_cooldown(tmp_path: Path, monkeypatch):
    org_a = tmp_path / "org_a" / "skills"
    org_b = tmp_path / "org_b" / "skills"
    org_a.mkdir(parents=True)
    org_b.mkdir(parents=True)
    (org_a / "a.py").write_text("def f(x):\n    return x\n", encoding="utf-8")
    (org_b / "b.py").write_text("def f(x):\n    return x + 1\n", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"

    from singular.runs.logger import RunLogger as RL

    monkeypatch.setattr(
        life_loop, "RunLogger", functools.partial(RL, root=tmp_path / "logs")
    )

    world = life_loop.WorldState(
        organisms={
            "org_a": life_loop.Organism(org_a, energy=4.8),
            "org_b": life_loop.Organism(org_b, energy=4.7),
        }
    )
    world.reproduction_cooldowns["org_a"] = 2

    run(
        {"org_a": org_a, "org_b": org_b},
        checkpoint,
        budget_seconds=0.2,
        max_iterations=1,
        rng=random.Random(0),
        run_id="repro-loop",
        operators={"dec": _dec_operator},
        world=world,
        ecosystem_rules=EcosystemRules(
            crossover_interval=1,
            reproduction_policy=ReproductionDecisionPolicy(compatibility_threshold=0.2),
        ),
    )

    events_path = tmp_path / "logs" / "repro-loop" / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    decisions = [
        e["payload"]
        for e in events
        if e.get("event_type") == "interaction"
        and e.get("payload", {}).get("interaction") == "reproduction_decision"
    ]
    assert decisions
    assert decisions[0]["accepted"] is False
    assert any("cooldown_active" in reason for reason in decisions[0]["reasons"])


def test_run_with_legacy_checkpoint_continues_without_crash(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "foo.py"
    skill.write_text("result = 1", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"
    checkpoint.write_text(json.dumps({"iteration": 2}), encoding="utf-8")

    state = run(
        skills_dir,
        checkpoint,
        budget_seconds=0.05,
        rng=random.Random(0),
        operators={"dec": _dec_operator},
    )

    saved = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert state.version == life_loop.CHECKPOINT_VERSION
    assert saved["version"] == life_loop.CHECKPOINT_VERSION
    assert saved["iteration"] >= 2


def test_health_history_retention_bounds_size() -> None:
    history = [
        {
            "iteration": i,
            "score": float(i),
            "performance": float(i) / 10.0,
            "acceptance_rate": 0.5,
            "sandbox_stability": 1.0,
            "energy_resources": 0.7,
            "failure_frequency": 0.1,
        }
        for i in range(1, 1001)
    ]

    retained = life_loop._retain_health_history(
        history,
        fine_window=50,
        aggregate_every=10,
    )

    expected_older = (1000 - 50) // 10
    assert len(retained) == expected_older + 50
    assert [point["iteration"] for point in retained[-50:]] == list(range(951, 1001))


def test_health_history_retention_preserves_trend_signal() -> None:
    history = [
        {
            "iteration": i,
            "score": float(i) / 2.0,
            "performance": 0.8,
            "acceptance_rate": 0.8,
            "sandbox_stability": 1.0,
            "energy_resources": 0.9,
            "failure_frequency": 0.0,
        }
        for i in range(1, 1201)
    ]
    original_scores = [point["score"] for point in history]

    retained = life_loop._retain_health_history(
        history,
        fine_window=200,
        aggregate_every=10,
    )
    retained_scores = [point["score"] for point in retained]

    assert detect_health_state(original_scores, short_window=20, long_window=100) == (
        "amélioration"
    )
    assert detect_health_state(retained_scores, short_window=20, long_window=100) == (
        "amélioration"
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


def _noop_operator(tree: ast.AST, rng=None) -> ast.AST:
    return tree


def test_run_nan_score_does_not_contaminate_stats(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "foo.py"
    skill.write_text("result = float('nan')", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"

    state = run(
        skills_dir,
        checkpoint,
        budget_seconds=0.05,
        rng=random.Random(0),
        operators={"noop": _noop_operator},
    )

    assert state.stats["noop"]["count"] >= 1
    assert state.stats["noop"]["reward"] == 0.0


def test_run_inf_score_does_not_contaminate_stats(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "foo.py"
    skill.write_text("result = float('inf')", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"

    state = run(
        skills_dir,
        checkpoint,
        budget_seconds=0.05,
        rng=random.Random(0),
        operators={"noop": _noop_operator},
    )

    assert state.stats["noop"]["count"] >= 1
    assert state.stats["noop"]["reward"] == 0.0


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
        budget_seconds=2.0,
        rng=random.Random(0),
        run_id="loop",
        operators=operators,
    )

    log_files = list((tmp_path / "logs").glob("loop-*.jsonl"))
    assert log_files
    entries = [json.loads(line) for line in log_files[0].read_text().splitlines()]
    used = {e["op"] for e in entries if "op" in e}
    assert "op1" in used or "op2" in used


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
        budget_seconds=0.3,
        rng=random.Random(0),
        run_id="loop1",
        operators=operators,
        mortality=life_loop.DeathMonitor(max_failures=100),
    )

    first_stats = load_checkpoint(checkpoint).stats
    assert first_stats["inc"]["count"] > 0
    assert first_stats["dec"]["count"] >= 0

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

        def log_consciousness(self, *a, **k):
            pass

    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    checkpoint = tmp_path / "ckpt.json"

    psyche = life_loop.Psyche()
    psyche.last_mood = Mood.FRUSTRATED
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

        def log_consciousness(self, *a, **k):
            pass

    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    checkpoint = tmp_path / "ckpt.json"

    psyche = life_loop.Psyche()
    psyche.last_mood = Mood.FRUSTRATED
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


def test_sandbox_violation_burst_enters_degraded_mode_without_immediate_extinction(
    tmp_path: Path, monkeypatch
):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "foo.py").write_text("result = 1", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"

    score_calls = {"n": 0}

    def failing_score(_code: str) -> float:
        score_calls["n"] += 1
        return float("-inf") if score_calls["n"] % 2 == 1 else 0.0

    monkeypatch.setattr(life_loop, "score_code", failing_score)
    monkeypatch.setattr(life_loop, "propose_mutations", lambda *_a, **_k: [])

    class StablePsyche:
        energy = 1000.0
        curiosity = 1.0
        patience = 1.0
        playfulness = 1.0
        sleeping = False

        def mutation_policy(self):
            return "default"

        def process_run_record(self, record):
            pass

        def save_state(self):
            pass

        def consume(self):
            pass

        def feel(self, mood):
            pass

    monkeypatch.setattr(life_loop.Psyche, "load_state", staticmethod(lambda: StablePsyche()))

    events: list[dict] = []
    bus = EventBus()
    bus.subscribe(
        "governance.degraded_mode_entered",
        lambda event: events.append(event.payload),
    )

    class FailureOnlyMonitor:
        def __init__(self, max_failures: int):
            self.max_failures = max_failures
            self.failures = 0

        def check(self, iteration, psyche, action_succeeded, resources=None):
            if not action_succeeded:
                self.failures += 1
            else:
                self.failures = 0
            if self.failures >= self.max_failures:
                return True, "too many failures"
            return False, None

    state = life_loop.run(
        skills_dir,
        checkpoint,
        budget_seconds=2.0,
        max_iterations=4,
        rng=random.Random(0),
        operators={"noop": _noop_operator},
        event_bus=bus,
        mortality=FailureOnlyMonitor(max_failures=10),
        world=life_loop.WorldState(
            organisms={
                skills_dir.name: life_loop.Organism(
                    skills_dir,
                    energy=1000.0,
                    resources=1000.0,
                    monitor=FailureOnlyMonitor(max_failures=10),
                )
            }
        ),
    )

    assert state.iteration >= life_loop.SANDBOX_DEGRADED_MODE_THRESHOLD
    assert events
    assert events[0]["sandbox_violation_streak"] >= life_loop.SANDBOX_DEGRADED_MODE_THRESHOLD


def test_prolonged_sandbox_violation_persistence_triggers_controlled_extinction(
    tmp_path: Path, monkeypatch
):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "foo.py").write_text("result = 1", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"

    score_calls = {"n": 0}

    def failing_score(_code: str) -> float:
        score_calls["n"] += 1
        return float("-inf") if score_calls["n"] % 2 == 1 else 0.0

    monkeypatch.setattr(life_loop, "score_code", failing_score)
    monkeypatch.setattr(life_loop, "propose_mutations", lambda *_a, **_k: [])
    monkeypatch.setattr(life_loop, "SANDBOX_DEGRADED_MODE_THRESHOLD", 1)
    monkeypatch.setattr(life_loop, "SANDBOX_EXTINCTION_THRESHOLD", 2)

    class StablePsyche:
        energy = 1000.0
        curiosity = 1.0
        patience = 1.0
        playfulness = 1.0
        sleeping = False

        def mutation_policy(self):
            return "default"

        def process_run_record(self, record):
            pass

        def save_state(self):
            pass

        def consume(self):
            pass

        def feel(self, mood):
            pass

    monkeypatch.setattr(life_loop.Psyche, "load_state", staticmethod(lambda: StablePsyche()))

    class FailureOnlyMonitor:
        def __init__(self, max_failures: int):
            self.max_failures = max_failures
            self.failures = 0

        def check(self, iteration, psyche, action_succeeded, resources=None):
            if not action_succeeded:
                self.failures += 1
            else:
                self.failures = 0
            if self.failures >= self.max_failures:
                return True, "too many failures"
            return False, None

    state = life_loop.run(
        skills_dir,
        checkpoint,
        budget_seconds=2.0,
        max_iterations=12,
        rng=random.Random(0),
        operators={"noop": _noop_operator},
        mortality=FailureOnlyMonitor(max_failures=1),
        world=life_loop.WorldState(
            organisms={
                skills_dir.name: life_loop.Organism(
                    skills_dir,
                    energy=1000.0,
                    resources=1000.0,
                    monitor=FailureOnlyMonitor(max_failures=1),
                )
            }
        ),
    )

    # Extinction occurs only once the higher sandbox violation threshold is crossed.
    assert state.iteration >= life_loop.SANDBOX_EXTINCTION_THRESHOLD
    assert state.iteration < 12


def _setup_dummy_psyche(monkeypatch, tmp_path, decisions):
    """Prepare a ``Psyche`` yielding predetermined ``decisions``."""

    decisions = list(decisions)
    episodes: list[dict] = []

    class DummyPsyche:
        last_mood = Mood.ANXIOUS

        def mutation_policy(self):
            return "default"

        def process_run_record(self, record):
            pass

        def save_state(self):
            pass

        def consume(self):
            pass

        def irrational_decision(self, rng=None):
            if decisions:
                return decisions.pop(0)
            return Psyche.Decision.ACCEPT

    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))
    monkeypatch.setattr(
        life_loop.Psyche, "load_state", staticmethod(lambda: DummyPsyche())
    )

    from singular.runs import logger as run_logger

    monkeypatch.setattr(
        life_loop,
        "RunLogger",
        functools.partial(run_logger.RunLogger, root=tmp_path / "logs"),
    )
    monkeypatch.setattr(life_loop, "update_score", lambda *a, **k: None)

    def fake_add_episode(ep, **k):
        episodes.append(ep)

    monkeypatch.setattr(life_loop, "add_episode", fake_add_episode)
    monkeypatch.setattr(run_logger, "add_episode", fake_add_episode)
    monkeypatch.setattr(life_loop, "capture_signals", lambda: {})

    return random.Random(0), episodes


def test_irrational_refusal(tmp_path: Path, monkeypatch):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "foo.py"
    skill.write_text("result = 1", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"

    rng, episodes = _setup_dummy_psyche(
        monkeypatch, tmp_path, [Psyche.Decision.REFUSE] * 1000
    )

    life_loop.run(
        skills_dir,
        checkpoint,
        budget_seconds=0.05,
        rng=rng,
        operators={"dec": _dec_operator},
    )

    assert skill.read_text(encoding="utf-8") == "result = 1"
    assert any(ep.get("event") == "refuse" for ep in episodes)


def test_irrational_delay(tmp_path: Path, monkeypatch):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "foo.py"
    skill.write_text("result = 1", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"

    rng, episodes = _setup_dummy_psyche(
        monkeypatch, tmp_path, [Psyche.Decision.DELAY, Psyche.Decision.ACCEPT]
    )

    life_loop.run(
        skills_dir,
        checkpoint,
        budget_seconds=0.1,
        rng=rng,
        operators={"dec": _dec_operator},
    )

    assert skill.read_text(encoding="utf-8") != "result = 1"
    assert any(ep.get("event") == "delay" for ep in episodes)


def test_irrational_curiosity(tmp_path: Path, monkeypatch):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "foo.py"
    skill.write_text("result = 1", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"

    rng, episodes = _setup_dummy_psyche(
        monkeypatch, tmp_path, [Psyche.Decision.CURIOUS] * 1000
    )

    life_loop.run(
        skills_dir,
        checkpoint,
        budget_seconds=0.05,
        rng=rng,
        operators={"dec": _dec_operator},
    )

    content = skill.read_text(encoding="utf-8")
    assert "mutation absurde" in content
    logs = list((tmp_path / "logs").glob("loop-*.jsonl"))
    assert logs, "log file not created"
    records = [json.loads(line) for line in logs[0].read_text().splitlines()]
    assert any(rec.get("event") == "absurde" for rec in records)
    assert any(ep.get("event") == "absurde" for ep in episodes)


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

    rm = ResourceManager(
        energy=50.0, food=30.0, warmth=50.0, path=tmp_path / "res.json"
    )

    calls = {"n": 0}
    original = life_loop.manage_resources

    def wrapped(*a, **k):
        calls["n"] += 1
        return original(*a, **k)

    monkeypatch.setattr(life_loop, "manage_resources", wrapped)

    run(
        skills_dir,
        checkpoint,
        budget_seconds=0.2,
        rng=random.Random(0),
        operators={"dec": _dec_operator},
        resource_manager=rm,
        test_runner=lambda: 3,
    )

    assert calls["n"] > 0
    assert rm.energy < 50.0
    assert rm.food >= 3.0
    assert Mood.FATIGUE not in events and Mood.ANGER not in events


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

    assert Mood.FATIGUE in events
    assert Mood.ANGER in events


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


def test_artifact_creation_persistence(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))

    import importlib
    from singular.environment import artifacts as env_artifacts

    importlib.reload(env_artifacts)

    from singular.environment.artifacts import (
        create_text_art,
        create_ascii_drawing,
        create_simple_melody,
        ARTIFACTS_DIR,
    )

    mood = "neutre"
    resources = {"energy": 1}
    text = create_text_art("bonjour", mood=mood, resources=resources)
    drawing = create_ascii_drawing(2, 2, mood=mood, resources=resources)
    melody = create_simple_melody(["C", "E", "G"], mood=mood, resources=resources)

    art_dir = tmp_path / "runs" / "artifacts"
    assert ARTIFACTS_DIR == art_dir

    for path in (text, drawing, melody):
        assert path.exists()
        assert path.parent == art_dir
        meta = json.loads((path.with_suffix(path.suffix + ".json")).read_text())
        assert meta["mood"] == mood
        assert meta["resources"] == resources
        assert "date" in meta


def test_coevolution_rejects_regression_on_combined_score(tmp_path: Path, monkeypatch):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "foo.py"
    skill.write_text("result = 1", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"

    from singular.runs.logger import RunLogger as RL

    monkeypatch.setattr(
        life_loop, "RunLogger", functools.partial(RL, root=tmp_path / "logs")
    )

    pool = LivingTestPool(tests=[TestCandidate("result == 1")], ttl={"result == 1": 3})
    run(
        skills_dir,
        checkpoint,
        budget_seconds=0.05,
        rng=random.Random(0),
        operators={"inc": _inc_operator},
        coevolve_tests=True,
        test_pool=pool,
        robustness_weight=2.0,
    )

    assert skill.read_text(encoding="utf-8") == "result = 1"


def test_coevolution_logs_decisions(tmp_path: Path, monkeypatch):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "foo.py").write_text("result = 1", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"

    from singular.runs.logger import RunLogger as RL

    monkeypatch.setattr(
        life_loop, "RunLogger", functools.partial(RL, root=tmp_path / "logs")
    )

    pool = LivingTestPool()
    run(
        skills_dir,
        checkpoint,
        budget_seconds=0.05,
        rng=random.Random(0),
        operators={"dec": _dec_operator},
        coevolve_tests=True,
        test_pool=pool,
    )

    log_file = next((tmp_path / "logs").glob("loop-*.jsonl"))
    records = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert any(rec.get("event") == "test_coevolution" for rec in records)


def test_governance_blocks_mutation_write(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "foo.py"
    skill.write_text("result = 1", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"

    policy = MutationGovernancePolicy(modifiable_paths=("allowed",))

    run(
        skills_dir,
        checkpoint,
        budget_seconds=0.1,
        rng=random.Random(0),
        operators={"dec": _dec_operator},
        governance_policy=policy,
    )

    assert _read_result(skill) == 1
