from __future__ import annotations

import argparse
import ast
import json
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from . import sandbox


@dataclass
class Checkpoint:
    """Simple persistent state for the evolutionary loop."""

    iteration: int = 0


def load_checkpoint(path: Path) -> Checkpoint:
    """Load checkpoint state from *path* if it exists."""

    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        return Checkpoint(**data)
    return Checkpoint()


def save_checkpoint(path: Path, state: Checkpoint) -> None:
    """Persist *state* to *path*."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state)), encoding="utf-8")


class _IncInt(ast.NodeTransformer):
    """Increment the first integer constant encountered."""

    def __init__(self) -> None:
        self.done = False

    def visit_Constant(self, node: ast.Constant) -> ast.AST:  # pragma: no cover - trivial
        if not self.done and isinstance(node.value, int):
            self.done = True
            return ast.copy_location(ast.Constant(node.value + 1), node)
        return node


def mutate(code: str) -> str:
    """Return *code* with one integer constant incremented by one."""

    tree = ast.parse(code)
    _IncInt().visit(tree)
    return ast.unparse(tree)


def score(code: str) -> float:
    """Execute *code* in the sandbox and return a numeric score.

    Non-numeric or failing executions yield ``-inf``.
    """

    try:
        result = sandbox.run(code)
    except Exception:
        return float("-inf")
    return float(result) if isinstance(result, (int, float)) else float("-inf")


def _choose_skill(rng: random.Random, skills: Iterable[Path]) -> Path:
    available = list(skills)
    if not available:
        raise RuntimeError("no skills available")
    return rng.choice(available)


def run(
    skills_dir: Path,
    checkpoint_path: Path,
    budget_seconds: float,
    rng: random.Random | None = None,
) -> Checkpoint:
    """Run the evolutionary loop for at most ``budget_seconds`` seconds."""

    rng = rng or random.Random()
    start = time.time()
    state = load_checkpoint(checkpoint_path)

    skills_dir.mkdir(parents=True, exist_ok=True)

    while time.time() - start < budget_seconds:
        state.iteration += 1

        skill_path = _choose_skill(rng, skills_dir.glob("*.py"))
        original = skill_path.read_text(encoding="utf-8")
        mutated = mutate(original)

        base_score = score(original)
        mutated_score = score(mutated)

        if mutated_score >= base_score:
            skill_path.write_text(mutated, encoding="utf-8")

        save_checkpoint(checkpoint_path, state)

    return state


def main(argv: list[str] | None = None) -> None:  # pragma: no cover - CLI wrapper
    parser = argparse.ArgumentParser(description="evolutionary life loop")
    parser.add_argument("--skills-dir", type=Path, default=Path("skills"))
    parser.add_argument(
        "--checkpoint", type=Path, default=Path("life_checkpoint.json")
    )
    parser.add_argument("--budget-seconds", type=float, required=True)
    args = parser.parse_args(argv)

    run(args.skills_dir, args.checkpoint, args.budget_seconds)


if __name__ == "__main__":  # pragma: no cover - module executable
    main()
