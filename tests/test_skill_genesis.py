import ast
import functools
import json
import random
from pathlib import Path

import singular.life.loop as life_loop
from singular.governance.policy import AUTH_REVIEW_REQUIRED, MutationGovernancePolicy
from singular.life.loop import run
from singular.life.skill_genesis import create_skill


def _dec_operator(tree: ast.AST, rng=None) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            node.value -= 1
            break
    return tree


def test_skill_genesis_creation_allowed(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))
    monkeypatch.setenv("SINGULAR_ROOT", str(tmp_path))
    skills_dir = tmp_path / "life" / "skills"
    mem_dir = tmp_path / "mem"
    skills_dir.mkdir(parents=True)
    (mem_dir / "skills.json").parent.mkdir(parents=True, exist_ok=True)
    (mem_dir / "skills.json").write_text("{}", encoding="utf-8")

    policy = MutationGovernancePolicy(
        modifiable_paths=("skills",),
        review_required_paths=("skills/review",),
        forbidden_paths=("src",),
        skill_creation_quota_per_window=2,
    )
    result = create_skill(
        skills_dir=skills_dir,
        mem_dir=mem_dir,
        governance_policy=policy,
        trigger="tech_debt",
        signal_snapshot={"tech_debt_markers": 12.0},
    )

    assert result.accepted is True
    assert result.target.exists()
    payload = json.loads((mem_dir / "skills.json").read_text(encoding="utf-8"))
    assert result.skill_name in payload
    assert (mem_dir / "skill_genesis.jsonl").exists()


def test_skill_genesis_creation_refused_by_policy(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))
    monkeypatch.setenv("SINGULAR_ROOT", str(tmp_path))
    skills_dir = tmp_path / "life" / "skills"
    mem_dir = tmp_path / "mem"
    skills_dir.mkdir(parents=True)

    policy = MutationGovernancePolicy(
        modifiable_paths=("skills",),
        review_required_paths=("skills/review",),
        forbidden_paths=("src",),
        file_creation_review_required=True,
    )
    result = create_skill(
        skills_dir=skills_dir,
        mem_dir=mem_dir,
        governance_policy=policy,
        trigger="coverage_gap",
        signal_snapshot={"coverage_gap": 0.9},
    )

    assert result.accepted is False
    assert result.policy_level == AUTH_REVIEW_REQUIRED
    assert not result.target.exists()


def test_skill_genesis_rolls_back_on_invalid_generation(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))
    monkeypatch.setenv("SINGULAR_ROOT", str(tmp_path))
    from singular.life import skill_genesis as genesis_mod

    skills_dir = tmp_path / "life" / "skills"
    mem_dir = tmp_path / "mem"
    skills_dir.mkdir(parents=True)
    mem_dir.mkdir(parents=True, exist_ok=True)
    (mem_dir / "skills.json").write_text(json.dumps({"keep": {"score": 1.0}}), encoding="utf-8")
    monkeypatch.setattr(genesis_mod, "_render_skill_template", lambda _name: "def bad(:\n")

    policy = MutationGovernancePolicy(
        modifiable_paths=("skills",),
        review_required_paths=("skills/review",),
        forbidden_paths=("src",),
    )
    result = genesis_mod.create_skill(
        skills_dir=skills_dir,
        mem_dir=mem_dir,
        governance_policy=policy,
        trigger="repeated_failures",
        signal_snapshot={"repeated_failures": 7.0},
    )

    assert result.accepted is False
    assert result.rolled_back is True
    assert not result.target.exists()
    restored = json.loads((mem_dir / "skills.json").read_text(encoding="utf-8"))
    assert restored == {"keep": {"score": 1.0}}


def test_skill_genesis_traceability_in_run_logs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))
    monkeypatch.setenv("SINGULAR_ROOT", str(tmp_path))
    skills_dir = tmp_path / "life" / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / "foo.py").write_text("result = 1\n", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"

    from singular.runs.logger import RunLogger as RL

    monkeypatch.setattr(
        life_loop, "RunLogger", functools.partial(RL, root=tmp_path / "logs")
    )
    monkeypatch.setattr(
        life_loop,
        "capture_signals",
        lambda **_kwargs: {
            "artifact_events": [
                {
                    "type": "artifact.tech_debt.simple",
                    "data": {"markers": 99},
                }
            ]
        },
    )

    policy = MutationGovernancePolicy(
        modifiable_paths=("skills",),
        review_required_paths=("skills/review",),
        forbidden_paths=("src",),
        skill_creation_quota_per_window=1,
    )
    run(
        skills_dir,
        checkpoint,
        budget_seconds=0.05,
        rng=random.Random(0),
        operators={"dec": _dec_operator},
        governance_policy=policy,
        max_iterations=1,
    )

    log_file = next((tmp_path / "logs").glob("loop-*.jsonl"))
    records = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
    assert any(rec.get("interaction") == "skill_genesis" for rec in records)
    journal = (tmp_path / "mem" / "skill_genesis.jsonl").read_text(encoding="utf-8").splitlines()
    assert journal
