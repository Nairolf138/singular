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
from typing import Callable, Dict, Iterable, Mapping

from singular.memory import add_episode, update_score
from singular.psyche import Psyche, Mood
from singular.runs.logger import RunLogger
from singular.runs.explain import summarize_mutation
from singular.organisms.spawn import mutation_absurde
from singular.perception import capture_signals, get_temperature
from graine.evolver.generate import propose_mutations
from singular.environment import artifacts as env_artifacts
from singular.environment import files as env_files
from singular.environment import notifications as env_notifications
from singular.resource_manager import ResourceManager

from . import sandbox
from .death import DeathMonitor
from .health import HealthTracker
from .reproduction import crossover
from .map_elites import MapElites
from .test_coevolution import LivingTestPool, propose_test_candidates

# mypy: ignore-errors

log = logging.getLogger(__name__)

# Energy management during the evolutionary loop. When the psyche's energy
# falls below ``SLEEP_THRESHOLD`` the organism will enter a sleeping phase for
# ``SLEEP_TICKS`` iterations where no mutations are attempted.
SLEEP_THRESHOLD = 10.0
SLEEP_TICKS = 5


@dataclass
class Checkpoint:
    """Simple persistent state for the evolutionary loop."""

    version: int = 1
    iteration: int = 0
    stats: Dict[str, Dict[str, float]] = field(default_factory=dict)
    health_history: list[dict[str, float | int]] = field(default_factory=list)
    health_counters: dict[str, float | int] = field(default_factory=dict)


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


OrganismInputs = Mapping[str, Path] | Iterable[Path] | Path

INTERACTION_RESOURCE_COMPETITION = "resource_competition"
INTERACTION_CROSSOVER = "crossover"
INTERACTION_EXTINCTION = "extinction"


CHECKPOINT_VERSION = 1


def _migrate_checkpoint_data(data: Mapping[str, object]) -> dict[str, object]:
    """Migrate checkpoint payload to the current schema version."""

    migrated = dict(data)
    version = migrated.get("version")
    if not isinstance(version, int):
        version = 0

    if version < 1:
        migrated["version"] = 1
        version = 1

    # Keep final payload aligned with current application schema.
    migrated["version"] = CHECKPOINT_VERSION
    return migrated


def _checkpoint_from_data(data: Mapping[str, object]) -> Checkpoint:
    """Build a :class:`Checkpoint` from raw persisted data safely."""

    migrated = _migrate_checkpoint_data(data)
    defaults = asdict(Checkpoint())
    payload = {**defaults, **migrated}
    allowed_keys = set(Checkpoint.__dataclass_fields__)
    filtered_payload = {key: value for key, value in payload.items() if key in allowed_keys}
    return Checkpoint(**filtered_payload)


def load_checkpoint(path: Path) -> Checkpoint:
    """Load checkpoint state from *path* if it exists."""

    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, json.JSONDecodeError) as exc:
            log.warning("failed to load checkpoint from %s: %s", path, exc)
        else:
            if isinstance(data, Mapping):
                return _checkpoint_from_data(data)
            log.warning("failed to load checkpoint from %s: root must be an object", path)
    return Checkpoint()


def save_checkpoint(path: Path, state: Checkpoint) -> None:
    """Persist *state* to *path*."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state)), encoding="utf-8")


def apply_mutation(
    code: str,
    operator: Callable[[ast.AST], ast.AST],
    rng: random.Random | None = None,
) -> str:
    """Return ``code`` transformed by ``operator``.

    The ``operator`` is expected to accept an :class:`ast.AST` instance and
    return a modified tree. If the operator supports a ``rng`` keyword
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


def select_operator(
    operators: Dict[str, Callable[[ast.AST], ast.AST]],
    stats: Dict[str, Dict[str, float]],
    policy: str,
    rng: random.Random,
) -> str:
    """Choose an operator name using an epsilon-greedy bandit policy."""

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


def score_code(code: str) -> float:
    """Execute ``code`` in the sandbox and return a numeric score.

    Non-numeric or failing executions yield ``-inf``.
    """

    try:
        result = sandbox.run(code)
    except Exception:
        return float("-inf")
    return float(result) if isinstance(result, (int, float)) else float("-inf")


def manage_resources(
    resource_manager: ResourceManager,
    cpu_seconds: float,
    test_runner: Callable[[], int] | None = None,
) -> list[str]:
    """Update resources according to CPU usage and test results.

    Returns the list of moods reported by ``resource_manager`` after
    consumption and replenishment steps.
    """

    resource_manager.consume_energy(cpu_seconds)
    if test_runner:
        try:
            passed = test_runner()
        except Exception:
            passed = 0
        resource_manager.add_food(passed)
    return resource_manager.mood()


def log_mutation(
    logger: RunLogger,
    iteration: int,
    key: str,
    op_name: str,
    diff: str,
    accepted: bool,
    ms_base: float,
    ms_new: float,
    base_score: float,
    mutated_score: float,
    impacted_file: str,
    loop_modifications: dict[str, int],
    health: dict[str, float | int] | None = None,
) -> None:
    """Record mutation outcome and notify observers."""

    env_notifications.notify(f"iteration {iteration}: {op_name}", channel=log.info)
    _ = env_files.list_files()
    if accepted:
        decision_reason = (
            "accepted: score improved or stayed equal"
            if mutated_score <= base_score
            else "accepted: non-score policy override"
        )
    else:
        decision_reason = "rejected: score regression or no measurable gain"

    human_summary = summarize_mutation(
        operator=op_name,
        impacted_file=impacted_file,
        accepted=accepted,
        diff=diff,
        ms_base=ms_base,
        ms_new=ms_new,
        score_base=base_score,
        score_new=mutated_score,
    )
    logger.log(
        key,
        op_name,
        diff,
        accepted,
        ms_base,
        ms_new,
        base_score,
        mutated_score,
        impacted_file=impacted_file,
        decision_reason=decision_reason,
        human_summary=human_summary,
        loop_modifications=loop_modifications,
        health=health,
    )


def _ast_node_count(tree: ast.AST) -> int:
    """Return the total number of nodes in ``tree``."""

    return sum(1 for _ in ast.walk(tree))


def _function_fingerprints(tree: ast.AST) -> dict[str, str]:
    """Build stable fingerprints for functions in ``tree``."""

    fingerprints: dict[str, str] = {}

    def visit(node: ast.AST, parents: tuple[str, ...]) -> None:
        if isinstance(node, ast.ClassDef):
            next_parents = parents + (node.name,)
        else:
            next_parents = parents
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            key = ".".join((*parents, node.name))
            fingerprints[key] = ast.dump(node, include_attributes=False)
            next_parents = (*parents, node.name)
        for child in ast.iter_child_nodes(node):
            visit(child, next_parents)

    visit(tree, ())
    return fingerprints


def _compute_loop_modifications(original: str, mutated: str) -> dict[str, int]:
    """Compute mutation diff metrics for loop reporting."""

    diff_lines = list(
        difflib.unified_diff(
            original.splitlines(),
            mutated.splitlines(),
            fromfile="original",
            tofile="mutated",
            lineterm="",
        )
    )
    added = sum(
        1 for line in diff_lines if line.startswith("+") and not line.startswith("+++")
    )
    removed = sum(
        1 for line in diff_lines if line.startswith("-") and not line.startswith("---")
    )

    before_tree = ast.parse(original)
    after_tree = ast.parse(mutated)
    before_functions = _function_fingerprints(before_tree)
    after_functions = _function_fingerprints(after_tree)

    changed = {
        name
        for name in (before_functions.keys() & after_functions.keys())
        if before_functions[name] != after_functions[name]
    }
    added_functions = after_functions.keys() - before_functions.keys()
    removed_functions = before_functions.keys() - after_functions.keys()

    return {
        "lines_added": added,
        "lines_removed": removed,
        "functions_modified": len(changed | added_functions | removed_functions),
        "ast_nodes_before": _ast_node_count(before_tree),
        "ast_nodes_after": _ast_node_count(after_tree),
    }


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


def _normalize_organism_inputs(skills_dirs: OrganismInputs) -> Dict[str, Path]:
    """Normalize organism inputs into a ``name -> skills_dir`` mapping."""

    if isinstance(skills_dirs, Path):
        return {skills_dirs.name: skills_dirs}
    if isinstance(skills_dirs, Mapping):
        normalized: Dict[str, Path] = {}
        for raw_name, raw_path in skills_dirs.items():
            name = str(raw_name)
            path = Path(raw_path)
            if name in normalized and normalized[name] != path:
                raise ValueError(
                    "organism key collision for "
                    f"'{name}': {normalized[name]} conflicts with {path}"
                )
            normalized[name] = path
        return normalized

    paths = [Path(path) for path in skills_dirs]
    normalized_paths: Dict[str, Path] = {}
    name_counts: Dict[str, int] = {}

    for path in paths:
        base_name = path.name
        next_index = name_counts.get(base_name, 1)
        unique_name = base_name if next_index == 1 else f"{base_name}#{next_index}"
        while unique_name in normalized_paths:
            next_index += 1
            unique_name = f"{base_name}#{next_index}"
        normalized_paths[unique_name] = path
        name_counts[base_name] = next_index + 1

    return normalized_paths


def run(
    skills_dirs: OrganismInputs,
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
    coevolve_tests: bool = False,
    test_pool: LivingTestPool | None = None,
    robustness_weight: float = 1.0,
    max_test_candidates: int = 3,
) -> Checkpoint:
    """Run the evolutionary loop for at most ``budget_seconds`` seconds.

    Parameters
    ----------
    skills_dirs:
        Organism inputs accepted as:
        - ``Path``: single organism.
        - ``Iterable[Path]``: multiple organisms (name inferred from folder).
        - ``Mapping[str, Path]``: explicit ``organism_name -> skills_dir`` contract.
    map_elites:
        Optional :class:`MapElites` instance. When provided, mutations are
        inserted into the MAP-Elites grid and only persisted if they improve
        their corresponding cell.
    """

    rng = rng or random.Random()
    state = load_checkpoint(checkpoint_path)

    organisms_input = _normalize_organism_inputs(skills_dirs)

    world = world or WorldState()
    for org_name, skills_dir in organisms_input.items():
        skills_dir.mkdir(parents=True, exist_ok=True)
        if org_name not in world.organisms:
            prototype = mortality or DeathMonitor()
            world.organisms[org_name] = Organism(skills_dir, monitor=prototype)

    operators = operators or _load_default_operators()
    stats: Dict[str, Dict[str, float]] = state.stats
    for name in operators:
        stats.setdefault(name, {"count": 0, "reward": 0.0})

    psyche = Psyche.load_state()
    resource_manager = resource_manager or ResourceManager()
    start = time.time()
    last_post = 0.0
    initial_freq = max(
        1,
        int(
            getattr(psyche, "mutation_rate", 1.0)
            * (getattr(psyche, "energy", 100.0) / 100)
        ),
    )
    for _ in range(initial_freq):
        propose_mutations([])
    mortality = mortality or DeathMonitor()
    seen_diffs: set[str] = set()
    sleep_ticks_remaining = 0
    if coevolve_tests and test_pool is None:
        test_pool = LivingTestPool()

    with RunLogger(run_id, psyche=psyche) as logger:
        health_tracker = HealthTracker.from_state(state.health_counters)
        delayed: list[tuple[float, str, Path]] = []
        while time.time() - start < budget_seconds:
            if getattr(psyche, "sleeping", False) or (
                hasattr(psyche, "energy")
                and getattr(psyche, "energy") < SLEEP_THRESHOLD
            ):
                if not getattr(psyche, "sleeping", False):
                    setattr(psyche, "sleeping", True)
                    sleep_ticks_remaining = SLEEP_TICKS
                if hasattr(psyche, "sleep_tick"):
                    psyche.sleep_tick()
                sleep_ticks_remaining -= 1
                if sleep_ticks_remaining <= 0:
                    setattr(psyche, "sleeping", False)
                if hasattr(psyche, "save_state"):
                    psyche.save_state()
                continue

            resource_manager.metabolize()
            signals = capture_signals()
            temp = get_temperature()
            signals["temperature"] = temp
            resource_manager.update_from_environment(temp)
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
            op_name = select_operator(operators, stats, policy, rng)
            mutated = apply_mutation(original, operators[op_name], rng)
            org = world.organisms[org_name]

            t0 = time.perf_counter()
            base_score = score_code(original)
            ms_base = (time.perf_counter() - t0) * 1000
            t0 = time.perf_counter()
            mutated_score = score_code(mutated)
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
            loop_modifications = _compute_loop_modifications(original, mutated)

            if diff not in seen_diffs:
                if hasattr(psyche, "feel"):
                    psyche.feel(Mood.CURIOUS)
                seen_diffs.add(diff)

            accepted = (
                map_elites.add(mutated, mutated_score)
                if map_elites
                else mutated_score <= base_score
            )
            detection_rate = 0.0
            test_delta = {"added": 0, "removed": 0}
            if coevolve_tests and test_pool is not None:
                detection_rate = test_pool.regression_detection_rate(original, mutated)
                combined_mutated = mutated_score + (robustness_weight * detection_rate)
                combined_base = base_score
                accepted = combined_mutated <= combined_base
                if accepted:
                    candidates = propose_test_candidates(mutated, rng, max_test_candidates)
                    test_delta = test_pool.evolve(mutated, candidates, rng)
                logger.log_test_coevolution(
                    skill=skill_path.stem,
                    accepted=accepted,
                    pool_size=len(test_pool.tests),
                    added=test_delta["added"],
                    removed=test_delta["removed"],
                    detection_rate=detection_rate,
                    score_base=base_score,
                    score_new=mutated_score,
                    score_combined_base=combined_base,
                    score_combined_new=combined_mutated,
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
                env_artifacts.save_text(f"mutation_{state.iteration}", diff)
            else:
                org.energy -= 0.1

            stats[op_name]["count"] += 1
            stats[op_name]["reward"] += base_score - mutated_score
            state.stats = stats

            # Resource accounting
            cpu_ms = ms_base + ms_new
            moods = manage_resources(resource_manager, cpu_ms / 1000.0, test_runner)
            resource_manager.consume_energy(0.5)
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

            sandbox_failure = (
                base_score == float("-inf") or mutated_score == float("-inf")
            )
            failed = sandbox_failure or (not accepted)
            health_snapshot = health_tracker.update(
                iteration=state.iteration,
                latency_ms=ms_new,
                accepted=accepted,
                sandbox_failure=sandbox_failure,
                energy=org.energy,
                resources=org.resources,
                failed=failed,
            )
            state.health_history.append(health_snapshot.to_dict())
            state.health_counters = health_tracker.to_state()

            logger.log_interaction(
                INTERACTION_RESOURCE_COMPETITION,
                organism=org_name,
                resource_pool=world.resource_pool,
                energy=org.energy,
                resources=org.resources,
                score=org.last_score,
                alive=True,
            )

            key = (
                f"{org_name}:{skill_path.stem}"
                if len(world.organisms) > 1
                else skill_path.stem
            )
            log_mutation(
                logger,
                state.iteration,
                key,
                op_name,
                diff,
                accepted,
                ms_base,
                ms_new,
                base_score,
                mutated_score,
                skill_path.name,
                loop_modifications,
                health=health_snapshot.to_dict(),
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
                logger.log_interaction(
                    INTERACTION_EXTINCTION,
                    organism=org_name,
                    reason=reason or "unknown",
                    alive=False,
                )
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
                logger.log_interaction(
                    INTERACTION_EXTINCTION,
                    organism=name,
                    reason="depleted_stores",
                    alive=False,
                )
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
                logger.log_interaction(
                    INTERACTION_CROSSOVER,
                    parents=parent_names,
                    child=child_dir.name,
                    child_skills_dir=str(child_dir),
                    alive=True,
                )

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
