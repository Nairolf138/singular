from pathlib import Path

import ast
import json
import pytest

from singular.organisms.spawn import spawn
from singular.governance.policy import MutationGovernancePolicy
from singular.life.reproduction import (
    InheritanceRules,
    ReproductionDecisionPolicy,
    ReproductionVariationPolicy,
    authorize_reproduction_write,
    decide_reproduction,
    crossover,
)
from singular.social.graph import SocialGraph


def test_reproduction(tmp_path: Path):
    parent_a = tmp_path / "parent_a"
    parent_b = tmp_path / "parent_b"

    # Skill setup
    (parent_a / "skills").mkdir(parents=True)
    (parent_b / "skills").mkdir(parents=True)
    (parent_a / "skills" / "skill_a.py").write_text(
        "def mix(x):\n    y = 1\n    z = x + y\n    return z\n",
        encoding="utf-8",
    )
    (parent_b / "skills" / "skill_b.py").write_text(
        "def mix(x):\n    y = 2\n    z = x * y\n    return z\n",
        encoding="utf-8",
    )

    # Psyche setup
    (parent_a / "mem").mkdir()
    (parent_b / "mem").mkdir()
    (parent_a / "mem" / "psyche.json").write_text(
        '{"curiosity": 0.2, "mood": "happy"}', encoding="utf-8"
    )
    (parent_b / "mem" / "psyche.json").write_text(
        '{"curiosity": 0.8, "mood": "sad"}', encoding="utf-8"
    )

    child_dir = spawn(parent_a, parent_b, out_dir=tmp_path / "child", seed=0)

    hybrids = list((child_dir / "skills").glob("hybrid_*.py"))
    assert hybrids, "no hybrid skills generated"
    code = hybrids[0].read_text(encoding="utf-8")
    ast.parse(code)
    assert "y = 1" in code and "return z" in code and "x * y" in code

    psyche = (child_dir / "mem" / "psyche.json").read_text(encoding="utf-8")
    import json

    state = json.loads(psyche)
    assert 0.0 <= state["curiosity"] <= 1.0
    assert state["curiosity"] == pytest.approx(0.5, abs=0.1)
    assert state["mood"] in {"happy", "sad"}


def test_reproduction_inherits_partial_memory(tmp_path: Path):
    parent_a = tmp_path / "parent_a"
    parent_b = tmp_path / "parent_b"
    (parent_a / "skills").mkdir(parents=True)
    (parent_b / "skills").mkdir(parents=True)
    (parent_a / "skills" / "skill_a.py").write_text(
        "def mix(x):\n    return x\n", encoding="utf-8"
    )
    (parent_b / "skills" / "skill_b.py").write_text(
        "def mix(x):\n    return x + 1\n", encoding="utf-8"
    )

    (parent_a / "mem").mkdir()
    (parent_b / "mem").mkdir()
    (parent_a / "mem" / "psyche.json").write_text(
        '{"curiosity": 0.2}', encoding="utf-8"
    )
    (parent_b / "mem" / "psyche.json").write_text(
        '{"curiosity": 0.8}', encoding="utf-8"
    )
    (parent_a / "mem" / "episodic.jsonl").write_text(
        '{"ts":"1","text":"a"}\n', encoding="utf-8"
    )
    (parent_b / "mem" / "episodic.jsonl").write_text(
        '{"ts":"2","text":"b"}\n', encoding="utf-8"
    )

    child = spawn(
        parent_a,
        parent_b,
        out_dir=tmp_path / "child",
        seed=1,
        inheritance_rules=InheritanceRules(
            inherit_partial_memory=True, memory_episode_limit=1
        ),
    )
    lines = (child / "mem" / "episodic.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_reproduction_blocks_incompatible_parents(tmp_path: Path):
    parent_a = tmp_path / "parent_a"
    parent_b = tmp_path / "parent_b"
    (parent_a / "skills").mkdir(parents=True)
    (parent_b / "skills").mkdir(parents=True)
    (parent_a / "skills" / "skill_a.py").write_text(
        "def mix(x):\n    return x\n", encoding="utf-8"
    )
    (parent_b / "skills" / "skill_b.py").write_text(
        "def mix(x):\n    return x + 1\n", encoding="utf-8"
    )
    (parent_a / "mem").mkdir()
    (parent_b / "mem").mkdir()
    (parent_a / "mem" / "psyche.json").write_text(
        '{"curiosity": 0.2}', encoding="utf-8"
    )
    (parent_b / "mem" / "psyche.json").write_text(
        '{"resilience": 0.8}', encoding="utf-8"
    )

    with pytest.raises(ValueError, match="compatibility"):
        spawn(
            parent_a,
            parent_b,
            out_dir=tmp_path / "child",
            seed=1,
            variation_policy=ReproductionVariationPolicy(compatibility_threshold=0.8),
        )


def test_reproduction_invalid_skill(tmp_path: Path):
    parent_a = tmp_path / "parent_a"
    parent_b = tmp_path / "parent_b"
    (parent_a / "skills").mkdir(parents=True)
    (parent_b / "skills").mkdir(parents=True)

    (parent_a / "skills" / "bad.py").write_text(
        "def mix(x):\n    y =\n",
        encoding="utf-8",
    )
    (parent_b / "skills" / "skill_b.py").write_text(
        "def mix(x):\n    return x\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid syntax"):
        spawn(parent_a, parent_b, out_dir=tmp_path / "child", seed=0)


def test_crossover_signature_mismatch(tmp_path: Path):
    parent_a = tmp_path / "parent_a"
    parent_b = tmp_path / "parent_b"
    parent_a.mkdir()
    parent_b.mkdir()

    (parent_a / "skill_a.py").write_text(
        "def mix(x):\n    return x\n",
        encoding="utf-8",
    )
    (parent_b / "skill_b.py").write_text(
        "def mix(x, y):\n    return x + y\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="matching signatures"):
        crossover(parent_a, parent_b)


def test_crossover_missing_return(tmp_path: Path):
    parent_a = tmp_path / "parent_a"
    parent_b = tmp_path / "parent_b"
    parent_a.mkdir()
    parent_b.mkdir()

    (parent_a / "skill_a.py").write_text(
        "def mix(x) -> int:\n    return x\n",
        encoding="utf-8",
    )
    (parent_b / "skill_b.py").write_text(
        "def mix(x) -> int:\n    y = x\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="return statement"):
        crossover(parent_a, parent_b)


def test_crossover_empty_ast(tmp_path: Path):
    parent_a = tmp_path / "parent_a"
    parent_b = tmp_path / "parent_b"
    parent_a.mkdir()
    parent_b.mkdir()

    (parent_a / "skill_a.py").write_text(
        "def mix(x):\n    return x\n",
        encoding="utf-8",
    )
    (parent_b / "empty.py").write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="function definition"):
        crossover(parent_a, parent_b)


def test_authorize_reproduction_write_blocked(tmp_path: Path):
    policy = MutationGovernancePolicy(modifiable_paths=("allowed",))
    target = tmp_path / "child" / "skills" / "hybrid.py"

    ok, reason = authorize_reproduction_write(target, "result = 1", policy)

    assert not ok
    assert "corrective_action" in reason
    assert not target.exists()


def test_reproduction_decision_refuses_incompatible_pair(tmp_path: Path):
    skills_a = tmp_path / "a" / "skills"
    skills_b = tmp_path / "b" / "skills"
    skills_a.mkdir(parents=True)
    skills_b.mkdir(parents=True)
    (skills_a / "sum.py").write_text("def sum_it(x):\n    return x\n", encoding="utf-8")
    (skills_b / "sum.py").write_text(
        "def sum_it(x):\n    return x + 1\n", encoding="utf-8"
    )

    social = SocialGraph(path=tmp_path / "mem" / "social_graph.json")
    for _ in range(8):
        social.update_relation("org-a", "org-b", "resource_conflict")

    decision = decide_reproduction(
        parent_a="org-a",
        parent_b="org-b",
        parent_a_skills=skills_a,
        parent_b_skills=skills_b,
        parent_a_health=0.2,
        parent_b_health=0.3,
        governance_allowed=True,
        social_graph=social,
        policy=ReproductionDecisionPolicy(
            compatibility_threshold=0.7,
            min_parent_health=0.4,
        ),
    )

    assert decision.accepted is False
    assert any(
        "compatibility_score_below_threshold" in reason for reason in decision.reasons
    )
    assert any("parent_health_below_min" in reason for reason in decision.reasons)


def test_reproduction_decision_accepts_high_affinity_and_viability(tmp_path: Path):
    skills_a = tmp_path / "a" / "skills"
    skills_b = tmp_path / "b" / "skills"
    skills_a.mkdir(parents=True)
    skills_b.mkdir(parents=True)
    (skills_a / "vision.py").write_text(
        "def solve(x):\n    return x\n", encoding="utf-8"
    )
    (skills_b / "planning.py").write_text(
        "def solve(x):\n    return x + 2\n", encoding="utf-8"
    )

    social = SocialGraph(path=tmp_path / "mem" / "social_graph.json")
    for _ in range(6):
        social.update_relation("org-a", "org-b", "successful_assistance")

    decision = decide_reproduction(
        parent_a="org-a",
        parent_b="org-b",
        parent_a_skills=skills_a,
        parent_b_skills=skills_b,
        parent_a_health=0.9,
        parent_b_health=0.85,
        governance_allowed=True,
        social_graph=social,
        policy=ReproductionDecisionPolicy(compatibility_threshold=0.6),
    )

    assert decision.accepted is True
    assert decision.score >= 0.6
    assert decision.components["social_affinity"] > 0.7
    assert decision.components["viability"] > 0.8


def _prepare_realistic_parent(
    life_dir: Path, *, skill_name: str, maturity: float = 0.86
) -> None:
    (life_dir / "skills").mkdir(parents=True, exist_ok=True)
    (life_dir / "mem").mkdir(parents=True, exist_ok=True)
    (life_dir / "skills" / f"{skill_name}.py").write_text(
        "def mix(x):\n    baseline = x + 1\n    return baseline\n",
        encoding="utf-8",
    )
    (life_dir / "mem" / "psyche.json").write_text(
        json.dumps({"curiosity": 0.7, "resilience": 0.8, "maturity_score": maturity}),
        encoding="utf-8",
    )
    (life_dir / "mem" / "skills.json").write_text(
        json.dumps({skill_name: {"inheritable": True, "level": 3}}),
        encoding="utf-8",
    )
    (life_dir / "mem" / "episodic.jsonl").write_text(
        "".join(
            json.dumps(
                {"event": "lesson", "status": "success", "text": f"{skill_name}-{idx}"}
            )
            + "\n"
            for idx in range(4)
        ),
        encoding="utf-8",
    )
    (life_dir / "mem" / "life_events.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    "event": "tick",
                    "status": "stable",
                    "mode": "normal",
                    "breaker": False,
                    "tick": idx,
                }
            )
            + "\n"
            for idx in range(5)
        ),
        encoding="utf-8",
    )


def test_realistic_reproduction_keeps_inheritance_and_files_scoped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from singular.cli import main
    from singular.lives import load_registry

    root = tmp_path / "root"
    monkeypatch.setenv("SINGULAR_ROOT", str(root))
    main(["--root", str(root), "lives", "create", "--name", "Alpha"])
    main(["--root", str(root), "lives", "create", "--name", "Beta"])
    registry = load_registry()
    alpha = registry["lives"]["alpha"]
    beta = registry["lives"]["beta"]
    _prepare_realistic_parent(alpha.path, skill_name="observe")
    _prepare_realistic_parent(beta.path, skill_name="plan")

    exit_code = main(
        [
            "--root",
            str(root),
            "--format",
            "json",
            "--seed",
            "4",
            "lives",
            "reproduce",
            "alpha",
            "beta",
            "--new-name",
            "Alpha Beta Child",
        ]
    )

    assert exit_code == 0
    updated = load_registry()
    child = updated["lives"]["alpha-beta-child"]
    assert updated["active"] == child.slug
    assert child.parents == ("alpha", "beta")
    assert child.slug in updated["lives"]["alpha"].children
    assert child.slug in updated["lives"]["beta"].children

    lineage = json.loads(
        (child.path / "mem" / "lineage.json").read_text(encoding="utf-8")
    )
    assert lineage["parents"] == ["alpha", "beta"]
    assert lineage["lineage_depth"] == 1

    inherited_memory = (
        (child.path / "mem" / "episodic.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert 0 < len(inherited_memory) <= 50
    assert all("lesson" in line for line in inherited_memory)
    child_skills = {path.name for path in (child.path / "skills").glob("*.py")}
    assert any(name.startswith("hybrid_") for name in child_skills)

    root_resolved = root.resolve()
    for path in child.path.rglob("*"):
        assert path.resolve().is_relative_to(root_resolved)


def test_lives_reproduction_reports_suspended_when_degraded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from singular.cli import main
    from singular.lives import load_registry

    root = tmp_path / "root"
    monkeypatch.setenv("SINGULAR_ROOT", str(root))
    main(["--root", str(root), "lives", "create", "--name", "Alpha"])
    main(["--root", str(root), "lives", "create", "--name", "Beta"])
    registry = load_registry()
    alpha = registry["lives"]["alpha"]
    beta = registry["lives"]["beta"]
    _prepare_realistic_parent(alpha.path, skill_name="observe")
    _prepare_realistic_parent(beta.path, skill_name="plan")
    (beta.path / "mem" / "reproduction_state.json").write_text(
        '{"mode":"degraded"}', encoding="utf-8"
    )

    main(
        [
            "--root",
            str(root),
            "lives",
            "reproduce",
            "alpha",
            "beta",
            "--new-name",
            "Paused Child",
        ]
    )

    out = capsys.readouterr().out
    assert "Reproduction suspendue" in out
    assert "degraded_mode" in out
    assert "paused-child" not in load_registry()["lives"]
