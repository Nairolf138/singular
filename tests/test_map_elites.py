import ast
import random
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parents[1]
sys.path.append(str(root_dir))
sys.path.append(str(root_dir / "src"))

from singular.life.coevolution_flow import MapElites  # noqa: E402
from singular.life.loop import run  # noqa: E402


def _inc_operator(tree: ast.AST, rng=None) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            node.value += 1
            break
    return tree


def test_distinct_regions_hold_unique_solutions():
    def descriptor(code: str, score: float) -> tuple[int, int]:
        val = int(code.split("=")[1])
        return (0 if val < 5 else 1, val % 2)

    me = MapElites(descriptor, bins=(2, 2))
    assert me.add("result = 1", 1)
    assert me.add("result = 6", 6)
    regions = me.regions()
    assert len(regions) == 2
    assert len(set(regions.values())) == 2


def test_loop_uses_map_elites_for_selection(tmp_path: Path, monkeypatch, local_sandbox):
    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path / "life-home"))
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "foo.py"
    skill.write_text("result = 0", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"

    def descriptor(code: str, score: float) -> tuple[int, int]:
        val = int(code.split("=")[1])
        return (0, val)

    me = MapElites(descriptor, bins=(1, 10))

    run(
        skills_dir,
        checkpoint,
        budget_seconds=1.0,
        max_iterations=1,
        rng=random.Random(0),
        operators={"inc": _inc_operator},
        map_elites=me,
    )

    # MAP-Elites records the candidate, while the fitness gate rejects the
    # regression before it can replace the working skill.
    assert skill.read_text(encoding="utf-8") == "result = 0"
    assert me.grid
