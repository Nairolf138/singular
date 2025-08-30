from __future__ import annotations

import argparse
import ast
import difflib
import importlib
import json
import logging
import random
import time
import heapq
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable

from singular.memory import add_episode, update_score
from singular.psyche import Psyche, Mood
from singular.runs.logger import RunLogger
from singular.organisms.spawn import mutation_absurde
from singular.perception import capture_signals
from graine.evolver.generate import propose_mutations
from singular.environment import artifacts as env_artifacts
from singular.environment import files as env_files
from singular.environment import notifications as env_notifications
from singular.resource_manager import ResourceManager

from . import sandbox
from .death import DeathMonitor
from .reproduction import crossover
from .map_elites import MapElites

# mypy: ignore-errors

log = logging.getLogger(__name__)


@dataclass
class Checkpoint:
    """Simple persistent state for the evolutionary loop."""

    iteration: int = 0
    stats: Dict[str, Dict[str, float]] = field(default_factory=dict)


@dataclass
class Organism:
    """State for a single organism participating in the loop."""

    skills_dir: Path
    last_score: float = float("-inf")
    energy: float = 1.0
    resources: float = 1.0
    monitor: DeathMonitor = field(default_factory=DeathMonitor)


@dataclass
class WorldState:
    """Shared state tracking all organisms and their interactions."""

    organisms: Dict[str, Organism] = field(default_factory=dict)
    resource_pool: float = 100.0


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


def _choose_skill(
    rng: random.Random, organisms: Dict[str, Organism]
) -> tuple[str, Path]:
    """Randomly choose an organism and one of its skills."""

    if not organisms:
        raise RuntimeError("no organisms available")

    org_name = rng.choice(list(organisms.keys()))
    org = organisms[org_name]
    available = list(org.skills_dir.glob("*.py"))
    if not available:
        raise RuntimeError(f"no skills available for organism {org_name}")
    return org_name, rng.choice(available)


def run(
    skills_dirs: Iterable[Path] | Path,
    checkpoint_path: Path,
    budget_seconds: float,
    rng: random.Random | None = None,
    run_id: str = "loop",
    operators: Dict[str, Callable[[ast.AST], ast.AST]] | None = None,
    mortality: DeathMonitor | None = None,
    world: WorldState | None = None,
    map_elites: MapElites | None = None,
    resource_manager: ResourceManager | None = None,
    test_runner: Callable[[], int] | None = None,
) -> Checkpoint:
    """Run the evolutionary loop for at most ``budget_seconds`` seconds.

    Parameters
    ----------
    skills_dirs:
        A collection of directories, each representing an organism and
        containing its skill files. A single :class:`~pathlib.Path` is accepted
        for backward compatibility.
    map_elites:
        Optional :class:`MapElites` instance. When provided, mutations are
        inserted into the MAP-Elites grid and only persisted if they improve
        their corresponding cell.
    """

    rng = rng or random.Random()
    state = load_checkpoint(checkpoint_path)

    if isinstance(skills_dirs, Path):
        skills_dirs = [skills_dirs]
    else:
        skills_dirs = list(skills_dirs)

    world = world or WorldState()
    for skills_dir in skills_dirs:
        skills_dir.mkdir(parents=True, exist_ok=True)
        if skills_dir.name not in world.organisms:
            prototype = mortality or DeathMonitor()
            world.organisms[skills_dir.name] = Organism(
                skills_dir, monitor=prototype
            )

    operators = operators or _load_default_operators()
    stats: Dict[str, Dict[str, float]] = state.stats
    for name in operators:
        stats.setdefault(name, {"count": 0, "reward": 0.0})

    psyche = Psyche.load_state()
    resource_manager = resource_manager or ResourceManager()
    start = time.time()
    last_post = 0.0
    freq = max(1, int(getattr(psyche, "mutation_rate", 1.0) * (getattr(psyche, "energy", 100.0) / 100)))
    for _ in range(freq):
        propose_mutations([])
    mortality = mortality or DeathMonitor()
    seen_diffs: set[str] = set()

    with RunLogger(run_id, psyche=psyche) as logger:
        delayed: list[tuple[float, str, Path]] = []
        while time.time() - start < budget_seconds:
            signals = capture_signals()
            add_episode({"event": "perception", **signals})
            state.iteration += 1

            now = time.time()
            if delayed and delayed[0][0] <= now:
                _, org_name, skill_path = heapq.heappop(delayed)
                decision = Psyche.Decision.ACCEPT
            else:
                org_name, skill_path = _choose_skill(rng, world.organisms)
                decision = Psyche.Decision.ACCEPT
                if hasattr(psyche, "irrational_decision"):
                    decision = psyche.irrational_decision(rng)

            original = skill_path.read_text(encoding="utf-8")

            if decision is Psyche.Decision.REFUSE:
                logger.log_refusal(skill_path.name)
                continue
            if decision is Psyche.Decision.DELAY:
                delay_until = time.time() + 0.01
                heapq.heappush(delayed, (delay_until, org_name, skill_path))
                logger.log_delay(skill_path.name, delay_until)
                continue
            if decision is Psyche.Decision.CURIOUS:
                mutated = mutation_absurde(original)
                diff = "".join(
                    difflib.unified_diff(
                        original.splitlines(True),
                        mutated.splitlines(True),
                        fromfile="original",
                        tofile="mutated",
                    )
                )
                skill_path.write_text(mutated, encoding="utf-8")
                logger.log_absurde(skill_path.name, diff)
                continue

            policy = psyche.mutation_policy()
            op_name = _select_operator(operators, stats, policy, rng)
            mutated = mutate(original, operators[op_name], rng)
            org = world.organisms[org_name]

            t0 = time.perf_counter()
            base_score = score(original)
            ms_base = (time.perf_counter() - t0) * 1000
            t0 = time.perf_counter()
            mutated_score = score(mutated)
            ms_new = (time.perf_counter() - t0) * 1000

            if mutated_score == float("-inf"):
                if hasattr(psyche, "feel"):
                    psyche.feel(Mood.PAIN)
            elif mutated_score <= base_score:
                if hasattr(psyche, "feel"):
                    psyche.feel(Mood.PLEASURE)

            diff = "".join(
                difflib.unified_diff(
                    original.splitlines(True),
                    mutated.splitlines(True),
                    fromfile="original",
                    tofile="mutated",
                )
            )

            if diff not in seen_diffs:
                if hasattr(psyche, "feel"):
                    psyche.feel(Mood.CURIOUS)
                seen_diffs.add(diff)

            accepted = (
                map_elites.add(mutated, mutated_score)
                if map_elites
                else mutated_score <= base_score
            )
            if accepted:
                skill_path.write_text(mutated, encoding="utf-8")
                key = (
                    f"{org_name}:{skill_path.stem}"
                    if len(world.organisms) > 1
                    else skill_path.stem
                )
                update_score(key, mutated_score)
                org.last_score = mutated_score
                org.energy += 0.2
                env_artifacts.save_text(
                    f"mutation_{state.iteration}", diff
                )
            else:
                org.energy -= 0.1

            env_notifications.notify(
                f"iteration {state.iteration}: {op_name}", channel=log.info
            )
            _ = env_files.list_files()

            stats[op_name]["count"] += 1
            stats[op_name]["reward"] += base_score - mutated_score
            state.stats = stats

            # Resource accounting
            cpu_ms = ms_base + ms_new
            resource_manager.consume_energy(cpu_ms / 1000.0)
            if test_runner:
                try:
                    passed = test_runner()
                except Exception:
                    passed = 0
                resource_manager.add_food(passed)

            moods = resource_manager.mood()
            if "tired" in moods:
                if hasattr(psyche, "feel"):
                    psyche.feel(Mood.FATIGUE)
                time.sleep(0.01)
            if "angry" in moods and hasattr(psyche, "feel"):
                psyche.feel(Mood.ANGER)
            if "cold" in moods and hasattr(psyche, "feel"):
                psyche.feel(Mood.LONELY)

            if time.time() - last_post >= 0.05:
                env_notifications.auto_post(
                    log.info,
                    (
                        f"moods={','.join(moods)} "
                        f"energy={resource_manager.energy:.1f} "
                        f"food={resource_manager.food:.1f} "
                        f"warmth={resource_manager.warmth:.1f}"
                    ),
                )
                last_post = time.time()

            # Shared resource competition
            if world.resource_pool > 0:
                world.resource_pool -= 1
                org.resources += 1
            else:
                org.resources -= 1

            for other in world.organisms.values():
                other.energy -= 0.05
                other.resources -= 0.02

            key = (
                f"{org_name}:{skill_path.stem}"
                if len(world.organisms) > 1
                else skill_path.stem
            )
            logger.log(
                key,
                op_name,
                diff,
                True,
                ms_base,
                ms_new,
                base_score,
                mutated_score,
            )

            if hasattr(psyche, "consume"):
                psyche.consume()
            if hasattr(psyche, "save_state"):
                psyche.save_state()

            save_checkpoint(checkpoint_path, state)

            dead, reason = org.monitor.check(
                state.iteration, psyche, mutated_score <= base_score, org.resources
            )
            if dead:
                logger.log_death(reason or "unknown", age=state.iteration)
                del world.organisms[org_name]
                if not world.organisms:
                    break
                continue

            # Remove organisms with depleted stores
            to_remove = [
                name
                for name, o in world.organisms.items()
                if o.energy <= 0 or o.resources <= 0
            ]
            for name in to_remove:
                del world.organisms[name]

            # Periodic crossover
            if state.iteration % 50 == 0 and len(world.organisms) >= 2:
                parent_names = rng.sample(list(world.organisms.keys()), 2)
                pa = world.organisms[parent_names[0]].skills_dir
                pb = world.organisms[parent_names[1]].skills_dir
                child_dir = pa.parent / f"child_{state.iteration}"
                child_dir.mkdir(parents=True, exist_ok=True)
                fname, code = crossover(pa, pb, rng)
                (child_dir / fname).write_text(code, encoding="utf-8")
                world.organisms[child_dir.name] = Organism(child_dir)

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
