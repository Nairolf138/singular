import json
import random
from pathlib import Path

import ast

import life.loop as life_loop
from life.loop import WorldState


def _inc_operator(tree: ast.AST, rng=None) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            node.value += 1
            break
    return tree


def _read_result(path: Path) -> int:
    return int(path.read_text(encoding="utf-8").split("=")[1])


def test_multi_organisms_independent(tmp_path: Path, monkeypatch):
    org1 = tmp_path / "org1"
    org2 = tmp_path / "org2"
    org1.mkdir()
    org2.mkdir()
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
        [org1, org2],
        checkpoint,
        budget_seconds=0.3,
        rng=random.Random(1),
        operators={"inc": _inc_operator},
        world=world,
    )
    life_loop.run(
        [org1, org2],
        checkpoint,
        budget_seconds=0.3,
        rng=random.Random(5),
        operators={"inc": _inc_operator},
        world=world,
    )

    val1 = _read_result(skill1)
    val2 = _read_result(skill2)
    assert val1 > 1
    assert val2 > 1

    scores = json.loads(mem_file.read_text())
    assert scores["org1:foo"]["score"] == val1
    assert scores["org2:foo"]["score"] == val2

    assert world.organisms["org1"].last_score == val1
    assert world.organisms["org2"].last_score == val2
