from __future__ import annotations

import argparse
import ast
import difflib
import importlib
import json
import logging
import random
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable

from singular.memory import update_score
from singular.psyche import Psyche
from singular.runs.logger import RunLogger

from . import sandbox
from .death import DeathMonitor

# mypy: ignore-errors

log = logging.getLogger(__name__)


@dataclass
class Checkpoint:
    """Simple persistent state for the evolutionary loop."""

    iteration: int = 0
    stats: Dict[str, Dict[str, float]] = field(default_factory=dict)


def load_checkpoint(path: Path) -> Checkpoint:
    """Load checkpoint state from *path* if it exists."""

    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("failed to load checkpoint from %s: %s", path, exc)
        else:
            return Checkpoint(**data)
    return Checkpoint()


def save_checkpoint(path: Path, state: Checkpoint) -> None:
    """Persist *state* to *path*."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state)), encoding="utf-8")


def mutate(
    code: str,
    operator: Callable[[ast.AST], ast.AST],
    rng: random.Random | None = None,
) -> str:
    """Return ``code`` transformed by ``operator``.

    The ``operator`` is expected to accept an :class:`ast.AST` instance and
    return a modified tree.  If the operator supports a ``rng`` keyword
    argument it will be passed the provided random number generator.
    """

    tree = ast.parse(code)
    try:
        new_tree = operator(tree, rng=rng)
    except TypeError:
        new_tree = operator(tree)
    return ast.unparse(new_tree)


def _load_default_operators() -> Dict[str, Callable[[ast.AST], ast.AST]]:
    """Load operators defined in :mod:`life.operators`."""

    from . import operators as ops

    loaded: Dict[str, Callable[[ast.AST], ast.AST]] = {}
    for name in getattr(ops, "__all__", []):
        mod = importlib.import_module(f"{__package__}.operators.{name}")
        loaded[name] = getattr(mod, "apply")
    return loaded


def _select_operator(
    operators: Dict[str, Callable[[ast.AST], ast.AST]],
    stats: Dict[str, Dict[str, float]],
    policy: str,
    rng: random.Random,
) -> str:
    """Choose an operator using an epsilon-greedy bandit policy."""

    names = list(operators.keys())

    if policy == "analyze":
        # deterministically explore least-used operator
        return min(names, key=lambda n: stats[n]["count"])

    epsilon = {"exploit": 0.0, "explore": 1.0}.get(policy, 0.1)

    if rng.random() < epsilon or all(stats[n]["count"] == 0 for n in names):
        return rng.choice(names)

    def expected(name: str) -> float:
        s = stats[name]
        return s["reward"] / s["count"] if s["count"] else 0.0

    return max(names, key=expected)


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
    run_id: str = "loop",
    operators: Dict[str, Callable[[ast.AST], ast.AST]] | None = None,
    mortality: DeathMonitor | None = None,
) -> Checkpoint:
    """Run the evolutionary loop for at most ``budget_seconds`` seconds."""

    rng = rng or random.Random()
    start = time.time()
    state = load_checkpoint(checkpoint_path)

    skills_dir.mkdir(parents=True, exist_ok=True)

    operators = operators or _load_default_operators()
    stats: Dict[str, Dict[str, float]] = state.stats
    for name in operators:
        stats.setdefault(name, {"count": 0, "reward": 0.0})

    psyche = Psyche.load_state()
    mortality = mortality or DeathMonitor()

    with RunLogger(run_id, psyche=psyche) as logger:
        while time.time() - start < budget_seconds:
            state.iteration += 1

            skill_path = _choose_skill(rng, skills_dir.glob("*.py"))
            original = skill_path.read_text(encoding="utf-8")

            policy = psyche.mutation_policy()
            op_name = _select_operator(operators, stats, policy, rng)
            mutated = mutate(original, operators[op_name], rng)

            t0 = time.perf_counter()
            base_score = score(original)
            ms_base = (time.perf_counter() - t0) * 1000
            t0 = time.perf_counter()
            mutated_score = score(mutated)
            ms_new = (time.perf_counter() - t0) * 1000

            diff = "".join(
                difflib.unified_diff(
                    original.splitlines(True),
                    mutated.splitlines(True),
                    fromfile="original",
                    tofile="mutated",
                )
            )

            if mutated_score >= base_score:
                skill_path.write_text(mutated, encoding="utf-8")
                update_score(skill_path.stem, mutated_score)

            stats[op_name]["count"] += 1
            stats[op_name]["reward"] += mutated_score - base_score
            state.stats = stats

            logger.log(
                skill_path.stem,
                op_name,
                diff,
                True,
                ms_base,
                ms_new,
                base_score,
                mutated_score,
            )

            save_checkpoint(checkpoint_path, state)

            dead, reason = mortality.check(
                state.iteration, psyche, mutated_score >= base_score
            )
            if dead:
                logger.log_death(reason or "unknown", age=state.iteration)
                psyche.save_state()
                break

    return state


def main(argv: list[str] | None = None) -> None:  # pragma: no cover - CLI wrapper
    parser = argparse.ArgumentParser(description="evolutionary life loop")
    parser.add_argument("--skills-dir", type=Path, default=Path("skills"))
    parser.add_argument("--checkpoint", type=Path, default=Path("life_checkpoint.json"))
    parser.add_argument("--budget-seconds", type=float, required=True)
    args = parser.parse_args(argv)

    run(args.skills_dir, args.checkpoint, args.budget_seconds)


if __name__ == "__main__":  # pragma: no cover - module executable
    main()
