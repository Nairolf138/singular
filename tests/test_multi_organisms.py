from pathlib import Path

import ast
import json
import random

import singular.life.loop as life_loop
from singular.life.loop import EcosystemRules, WorldState
from singular.dashboard import create_app
from fastapi_stub import TestClient


def _dec_operator(tree: ast.AST, rng=None) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            node.value -= 1
            break
    return tree


def _read_result(path: Path) -> int:
    return int(path.read_text(encoding="utf-8").split("=")[1])


def test_multi_organisms_independent(tmp_path: Path, monkeypatch):
    org1 = tmp_path / "org1" / "skills"
    org2 = tmp_path / "org2" / "skills"
    org1.mkdir(parents=True)
    org2.mkdir(parents=True)
    skill1 = org1 / "foo.py"
    skill2 = org2 / "foo.py"
    skill1.write_text("result = 1", encoding="utf-8")
    skill2.write_text("result = 1", encoding="utf-8")

    checkpoint = tmp_path / "ckpt.json"
    mem_file = tmp_path / "scores.json"

    def fake_update_score(skill: str, score: float) -> None:
        data = json.loads(mem_file.read_text()) if mem_file.exists() else {}
        data[skill] = {"score": score}
        mem_file.write_text(json.dumps(data))

    monkeypatch.setattr(life_loop, "update_score", fake_update_score)

    world = WorldState()
    life_loop.run(
        {"org1": org1, "org2": org2},
        checkpoint,
        budget_seconds=0.3,
        rng=random.Random(1),
        operators={"dec": _dec_operator},
        world=world,
    )
    life_loop.run(
        {"org1": org1, "org2": org2},
        checkpoint,
        budget_seconds=0.3,
        rng=random.Random(5),
        operators={"dec": _dec_operator},
        world=world,
    )

    val1 = _read_result(skill1)
    val2 = _read_result(skill2)
    assert val1 < 1
    assert val2 < 1

    scores = json.loads(mem_file.read_text())
    assert scores["org1:foo"]["score"] == val1
    assert scores["org2:foo"]["score"] == val2

    assert world.organisms["org1"].last_score == val1
    assert world.organisms["org2"].last_score == val2


def test_multi_organism_events_and_dashboard(tmp_path: Path, monkeypatch) -> None:
    org1 = tmp_path / "org1" / "skills"
    org2 = tmp_path / "org2" / "skills"
    org1.mkdir(parents=True)
    org2.mkdir(parents=True)
    (org1 / "foo.py").write_text("result = 1", encoding="utf-8")
    (org2 / "foo.py").write_text("result = 1", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"
    runs_dir = tmp_path / "runs"

    from singular.runs.logger import RunLogger as RL

    monkeypatch.setattr(
        life_loop, "RunLogger", lambda *a, **k: RL(*a, root=runs_dir, **k)
    )
    world = WorldState(resource_pool=0.0)
    life_loop.run(
        {"org1": org1, "org2": org2},
        checkpoint,
        budget_seconds=0.2,
        rng=random.Random(2),
        operators={"dec": _dec_operator},
        world=world,
    )

    log_file = next(runs_dir.glob("loop-*.jsonl"))
    rows = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
    interactions = [row for row in rows if row.get("event") == "interaction"]
    assert any(
        row.get("interaction") == life_loop.INTERACTION_RESOURCE_COMPETITION
        for row in interactions
    )

    app = create_app(runs_dir=runs_dir, psyche_file=tmp_path / "missing_psyche.json")
    client = TestClient(app)
    ecosystem = client.get("/ecosystem").json()
    assert ecosystem["organisms"]
    assert ecosystem["summary"]["total_organisms"] >= 1


def test_normalize_organism_inputs_iterable_auto_renames_collisions(
    tmp_path: Path,
) -> None:
    first = tmp_path / "set_a" / "skills"
    second = tmp_path / "set_b" / "skills"
    third = tmp_path / "set_c" / "skills"

    normalized = life_loop._normalize_organism_inputs([first, second, third])

    assert list(normalized.keys()) == ["skills", "skills#2", "skills#3"]
    assert normalized["skills"] == first
    assert normalized["skills#2"] == second
    assert normalized["skills#3"] == third


def test_normalize_organism_inputs_mapping_collision_raises_clear_error(
    tmp_path: Path,
) -> None:
    one = tmp_path / "org_one"
    two = tmp_path / "org_two"

    # str(1) and "1" normalize to the same organism key.
    mapping = {1: one, "1": two}

    try:
        life_loop._normalize_organism_inputs(mapping)
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected ValueError for key collision")

    assert "organism key collision for '1'" in message
    assert str(one) in message
    assert str(two) in message


def test_ecosystem_rules_and_reputation_influence_crossover(tmp_path: Path) -> None:
    org1 = tmp_path / "org1" / "skills"
    org2 = tmp_path / "org2" / "skills"
    org1.mkdir(parents=True)
    org2.mkdir(parents=True)
    (org1 / "foo.py").write_text(
        "def solve(x):\n    return x\n",
        encoding="utf-8",
    )
    (org2 / "foo.py").write_text(
        "def solve(x):\n    return x + 1\n",
        encoding="utf-8",
    )
    checkpoint = tmp_path / "ckpt.json"
    world = WorldState(resource_pool=2.0)
    world.reputation.reputations["org1"] = 2.0
    world.reputation.reputations["org2"] = -1.0
    rules = EcosystemRules(
        resource_competition_unit=0.5,
        passive_energy_decay=0.0,
        passive_resource_decay=0.0,
        crossover_interval=1,
    )

    life_loop.run(
        {"org1": org1, "org2": org2},
        checkpoint,
        budget_seconds=0.3,
        rng=random.Random(3),
        operators={"dec": _dec_operator},
        world=world,
        ecosystem_rules=rules,
    )

    # Resource competition uses rule-defined increment/decrement unit.
    assert world.resource_pool <= 1.5
    assert "child_1" in world.organisms
