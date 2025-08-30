from pathlib import Path

import ast
import pytest

from singular.organisms.spawn import spawn
from life.reproduction import crossover


def test_reproduction(tmp_path: Path):
    parent_a = tmp_path / "parent_a"
    parent_b = tmp_path / "parent_b"
    parent_a.mkdir()
    parent_b.mkdir()

    (parent_a / "skill_a.py").write_text(
        "def mix(x):\n    y = 1\n    z = x + y\n    return z\n",
        encoding="utf-8",
    )
    (parent_b / "skill_b.py").write_text(
        "def mix(x):\n    y = 2\n    z = x * y\n    return z\n",
        encoding="utf-8",
    )

    child_dir = spawn(parent_a, parent_b, out_dir=tmp_path / "child", seed=0)
    hybrids = list(child_dir.glob("hybrid_*.py"))
    assert hybrids, "no hybrid skills generated"
    code = hybrids[0].read_text(encoding="utf-8")
    ast.parse(code)
    assert "y = 1" in code and "return z" in code and "x * y" in code


def test_reproduction_invalid_skill(tmp_path: Path):
    parent_a = tmp_path / "parent_a"
    parent_b = tmp_path / "parent_b"
    parent_a.mkdir()
    parent_b.mkdir()

    (parent_a / "bad.py").write_text(
        "def mix(x):\n    y =\n",
        encoding="utf-8",
    )
    (parent_b / "skill_b.py").write_text(
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
