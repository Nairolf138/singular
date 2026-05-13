import ast
import functools
import json
import random
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parents[1]
sys.path.append(str(root_dir))
sys.path.append(str(root_dir / "src"))

import singular.life.loop as life_loop  # noqa: E402
from graine.evolver.dsl import Patch  # noqa: E402
from singular.governance.policy import MutationGovernancePolicy  # noqa: E402


def _dec_operator(tree: ast.AST, rng=None) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            node.value -= 1
            break
    return tree


def _dangerous_open_operator(tree: ast.AST, rng=None) -> ast.AST:
    return ast.parse("result = open('secret.txt')")


def _stable_psyche(monkeypatch):
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

    monkeypatch.setattr(
        life_loop.Psyche, "load_state", staticmethod(lambda: StablePsyche())
    )


def _graine_const_tune_patch(target: str = "skills/foo.py") -> Patch:
    return Patch.from_dict(
        {
            "target": {"file": target, "function": "foo"},
            "ops": [{"op": "CONST_TUNE"}],
            "theta_diff": 0.0,
            "purity": True,
            "cyclomatic": 1,
        }
    )


def _run_graine_case(tmp_path: Path, monkeypatch, operator, *, governance_policy):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "foo.py"
    skill.write_text("result = 1\n", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"
    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))
    monkeypatch.setattr(life_loop, "SKILL_GENESIS_TECH_DEBT_THRESHOLD", 10_000)
    monkeypatch.setattr(life_loop, "SKILL_GENESIS_FAILURE_STREAK_THRESHOLD", 10_000)
    monkeypatch.setattr(life_loop, "SKILL_GENESIS_COVERAGE_GAP_THRESHOLD", 10_000.0)
    _stable_psyche(monkeypatch)

    calls = []

    def fake_propose(zones=None):
        calls.append(zones)
        if zones == []:
            return []
        return [_graine_const_tune_patch(str(skill))]

    monkeypatch.setattr(life_loop, "propose_mutations", fake_propose)

    from singular.runs.logger import RunLogger as RL

    monkeypatch.setattr(
        life_loop, "RunLogger", functools.partial(RL, root=tmp_path / "logs")
    )

    life_loop.run(
        skills_dir,
        checkpoint,
        budget_seconds=10.0,
        max_iterations=1,
        rng=random.Random(0),
        operators={"CONST_TUNE": operator},
        governance_policy=governance_policy,
    )
    events_path = tmp_path / "logs" / "loop" / "events.jsonl"
    events = [
        json.loads(line)
        for line in events_path.read_text(encoding="utf-8").splitlines()
    ]
    return skill, calls, events


def _event_payloads(events: list[dict], event_type: str) -> list[dict]:
    return [
        event["payload"] for event in events if event.get("event_type") == event_type
    ]


def test_graine_proposed_mutation_is_blocked_by_governance(tmp_path, monkeypatch):
    policy = MutationGovernancePolicy(modifiable_paths=("not_skills",))
    skill, calls, events = _run_graine_case(
        tmp_path,
        monkeypatch,
        _dec_operator,
        governance_policy=policy,
    )

    assert any(call and call[0]["operators"] == ["CONST_TUNE"] for call in calls)
    assert skill.read_text(encoding="utf-8") == "result = 1\n"
    violations = [
        payload
        for payload in _event_payloads(events, "interaction")
        if payload.get("interaction") == "governance_violation"
    ]
    assert violations
    assert violations[0]["target"] == str(skill)


def test_graine_proposed_mutation_is_rejected_by_sandbox(tmp_path, monkeypatch):
    policy = MutationGovernancePolicy(modifiable_paths=("skills",))
    skill, _calls, events = _run_graine_case(
        tmp_path,
        monkeypatch,
        _dangerous_open_operator,
        governance_policy=policy,
    )

    assert skill.read_text(encoding="utf-8") == "result = 1\n"
    diagnostics = [
        payload
        for payload in _event_payloads(events, "interaction")
        if payload.get("interaction") == "sandbox_violation"
    ]
    assert diagnostics
    assert (
        diagnostics[0]["sandbox_violation_category"] == "dangerous_mutation_violation"
    )
    assert diagnostics[0]["dangerous_mutation_pattern"] is True
