from pathlib import Path

from singular.organisms.spawn import spawn


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
    assert "y = 1" in code and "return z" in code and "x * y" in code
