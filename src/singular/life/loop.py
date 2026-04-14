from __future__ import annotations

import argparse
import ast
import difflib
import importlib
import json
import logging
import math
import random
import time
import heapq
import hashlib
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, Mapping

from singular.cognition.reflect import ActionHypothesis, reflect_action
from singular.beliefs.store import BeliefStore
from singular.beliefs.meta_learning import (
    extract_run_features,
    recommend_strategy,
    register_run_result,
)
from singular.events import EventBus, get_global_event_bus
from singular.memory import register_memory_event_handlers, update_score
from singular.psyche import Psyche, Mood
from singular.runs.logger import RunLogger
from singular.runs.explain import summarize_mutation
from singular.runs.generations import record_generation
from singular.organisms.spawn import mutation_absurde
from singular.perception import capture_signals, get_temperature
from graine.evolver.generate import propose_mutations
from singular.environment import artifacts as env_artifacts
from singular.environment import files as env_files
from singular.environment import notifications as env_notifications
from singular.environment.reputation import ReputationSystem
from singular.environment.world_resources import CompetitorIntent, WorldResourcePool
from singular.goals import IntrinsicGoals
from singular.resource_manager import ResourceManager

from . import sandbox
from .death import DeathMonitor
from .health import HealthTracker
from singular.governance.policy import MutationGovernancePolicy
from singular.governance.values import load_value_weights

from .reproduction import authorize_reproduction_write, crossover
from .map_elites import MapElites
from .test_coevolution import LivingTestPool, propose_test_candidates
from .skill_genesis import create_skill

# mypy: ignore-errors

log = logging.getLogger(__name__)

# Energy management during the evolutionary loop. When the psyche's energy
# falls below ``SLEEP_THRESHOLD`` the organism will enter a sleeping phase for
# ``SLEEP_TICKS`` iterations where no mutations are attempted.
SLEEP_THRESHOLD = 10.0
SLEEP_TICKS = 5
SKILL_GENESIS_TECH_DEBT_THRESHOLD = 8
SKILL_GENESIS_FAILURE_STREAK_THRESHOLD = 3
SKILL_GENESIS_COVERAGE_GAP_THRESHOLD = 0.6


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
    reputation: ReputationSystem = field(default_factory=ReputationSystem)
    world_resources: WorldResourcePool = field(default_factory=WorldResourcePool)


@dataclass
class EcosystemRules:
    """Configurable local ecosystem rules for interactions."""

    resource_competition_unit: float = 1.0
    passive_energy_decay: float = 0.05
    passive_resource_decay: float = 0.02
    crossover_interval: int = 50
    cooperation_probability: float = 0.2
    competition_bid_ceiling: float = 5.0
    reputation_action_weights: dict[str, float] = field(
        default_factory=lambda: {"share": 0.2, "steal": -0.2}
    )


OrganismInputs = Mapping[str, Path] | Iterable[Path] | Path

INTERACTION_RESOURCE_COMPETITION = "resource_competition"
INTERACTION_CROSSOVER = "crossover"
INTERACTION_EXTINCTION = "extinction"


CHECKPOINT_VERSION = 1
HEALTH_HISTORY_FINE_WINDOW = 500
HEALTH_HISTORY_AGGREGATE_EVERY = 10


def _aggregate_health_bucket(
    bucket: list[dict[str, float | int]],
) -> dict[str, float | int]:
    """Aggregate a bucket of health snapshots into one representative point."""

    if not bucket:
        return {}

    keys = bucket[0].keys()
    aggregated: dict[str, float | int] = {}
    for key in keys:
        if key == "iteration":
            aggregated[key] = int(bucket[-1].get("iteration", 0))
            continue
        values = [float(point.get(key, 0.0)) for point in bucket]
        aggregated[key] = sum(values) / len(values)
    return aggregated


def _retain_health_history(
    history: list[dict[str, float | int]],
    *,
    fine_window: int = HEALTH_HISTORY_FINE_WINDOW,
    aggregate_every: int = HEALTH_HISTORY_AGGREGATE_EVERY,
) -> list[dict[str, float | int]]:
    """Retain recent detailed points and periodically aggregate older samples."""

    if fine_window <= 0:
        fine_window = 1
    if aggregate_every <= 1:
        aggregate_every = 1
    if len(history) <= fine_window:
        return list(history)

    older = history[:-fine_window]
    recent = history[-fine_window:]
    retained: list[dict[str, float | int]] = []
    for start in range(0, len(older), aggregate_every):
        bucket = older[start : start + aggregate_every]
        retained.append(_aggregate_health_bucket(bucket))
    retained.extend(recent)
    return retained


def _should_trigger_skill_genesis(
    *,
    signals: Mapping[str, object],
    health_counters: Mapping[str, float | int],
) -> tuple[bool, str, dict[str, float]]:
    tech_debt_markers = 0.0
    artifact_events = signals.get("artifact_events")
    if isinstance(artifact_events, list):
        for event in artifact_events:
            if not isinstance(event, Mapping):
                continue
            if event.get("type") != "artifact.tech_debt.simple":
                continue
            data = event.get("data")
            if not isinstance(data, Mapping):
                continue
            try:
                tech_debt_markers = float(data.get("markers", 0.0))
            except (TypeError, ValueError):
                tech_debt_markers = 0.0
            break
    repeated_failures = float(health_counters.get("consecutive_failures", 0.0))
    total = max(float(health_counters.get("total", 0.0)), 1.0)
    accepted = float(health_counters.get("accepted", 0.0))
    coverage_gap = 1.0 - (accepted / total)
    functional_gap_signal = signals.get("functional_coverage_gap")
    if isinstance(functional_gap_signal, (int, float)):
        coverage_gap = max(coverage_gap, float(functional_gap_signal))
    snapshot = {
        "tech_debt_markers": tech_debt_markers,
        "repeated_failures": repeated_failures,
        "coverage_gap": coverage_gap,
    }
    if tech_debt_markers >= SKILL_GENESIS_TECH_DEBT_THRESHOLD:
        return True, "tech_debt", snapshot
    if repeated_failures >= SKILL_GENESIS_FAILURE_STREAK_THRESHOLD:
        return True, "repeated_failures", snapshot
    if coverage_gap >= SKILL_GENESIS_COVERAGE_GAP_THRESHOLD:
        return True, "coverage_gap", snapshot
    return False, "", snapshot


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
    objective_bias: Mapping[str, float] | None = None,
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
        exploitation = s["reward"] / s["count"] if s["count"] else 0.0
        return exploitation + float((objective_bias or {}).get(name, 0.0))

    return max(names, key=expected)


def score_code(code: str) -> float:
    """Execute ``code`` in the sandbox and return a numeric score.

    Non-numeric or failing executions yield ``-inf``.
    """

    try:
        result = sandbox.run(code)
    except Exception:
        return float("-inf")
    if not isinstance(result, (int, float)):
        return float("-inf")
    score = float(result)
    return score if math.isfinite(score) else float("-inf")


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


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


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
    alternative_scores: list[tuple[int, str, float]] | None = None,
    decision_reason: str | None = None,
    health: dict[str, float | int] | None = None,
) -> None:
    """Record mutation outcome and notify observers."""

    env_notifications.notify(f"iteration {iteration}: {op_name}", channel=log.info)
    _ = env_files.list_files()
    if decision_reason is None and accepted:
        decision_reason = (
            "accepted: score improved or stayed equal"
            if mutated_score <= base_score
            else "accepted: non-score policy override"
        )
    elif decision_reason is None:
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
    reward_delta = base_score - mutated_score
    perceived_quality = _clamp01(0.5 + (reward_delta * 0.5))
    user_satisfaction = _clamp01(
        (0.65 if accepted else 0.15) + (0.35 * perceived_quality)
    )
    usage_metrics = {
        "success": accepted,
        "latency_ms": ms_new,
        "resource_cost": ms_base + ms_new,
        "perceived_quality": perceived_quality,
        "user_satisfaction": user_satisfaction,
    }
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
        alternative_scores=alternative_scores or [],
        human_summary=human_summary,
        loop_modifications=loop_modifications,
        health=health,
        usage_metrics=usage_metrics,
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
    rng: random.Random,
    organisms: Dict[str, Organism],
    skill_reputation: Mapping[str, Mapping[str, float | int]] | None = None,
) -> tuple[str, Path]:
    """Choose a skill with utility-aware priority and exploration fallback."""

    if not organisms:
        raise RuntimeError("no organisms available")

    candidates: list[tuple[str, Path]] = []
    for org_name, org in organisms.items():
        available = list(org.skills_dir.glob("*.py"))
        for skill_path in available:
            candidates.append((org_name, skill_path))
    if not candidates:
        raise RuntimeError("no skills available for any organism")

    def priority(org_name: str, skill_path: Path) -> float:
        key = (
            f"{org_name}:{skill_path.stem}"
            if len(organisms) > 1
            else skill_path.stem
        )
        rep = dict((skill_reputation or {}).get(key, {}))
        quality = float(rep.get("mean_quality", 0.5))
        use_count = float(rep.get("use_count", 0.0))
        success_rate = float(rep.get("success_rate", 0.5))
        recent_failures = float(rep.get("recent_failures", 0.0))
        # Trigger rule: frequently used + low quality => targeted mutation.
        targeted_mutation = 1.5 if use_count >= 5.0 and quality <= 0.45 else 0.0
        return (
            1.0
            + (1.0 - quality) * 0.8
            + use_count * 0.03
            + recent_failures * 0.1
            + (1.0 - success_rate) * 0.4
            + targeted_mutation
        )

    weighted = [(org_name, skill_path, max(0.01, priority(org_name, skill_path))) for org_name, skill_path in candidates]
    total = sum(weight for _, _, weight in weighted)
    pick = rng.random() * total
    cumulative = 0.0
    for org_name, skill_path, weight in weighted:
        cumulative += weight
        if cumulative >= pick:
            return org_name, skill_path
    fallback_org, fallback_skill, _ = weighted[-1]
    return fallback_org, fallback_skill


def _pick_crossover_parents(rng: random.Random, world: WorldState) -> tuple[str, str]:
    """Prefer high-reputation organisms when selecting crossover parents."""

    names = list(world.organisms.keys())
    weighted = sorted(
        names,
        key=lambda name: world.reputation.get(name),
        reverse=True,
    )
    primary = weighted[0]
    remaining = [name for name in names if name != primary]
    return primary, rng.choice(remaining)


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
    event_bus: EventBus | None = None,
    governance_policy: MutationGovernancePolicy | None = None,
    max_iterations: int | None = None,
    ecosystem_rules: EcosystemRules | None = None,
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
    state.health_history = _retain_health_history(state.health_history)

    organisms_input = _normalize_organism_inputs(skills_dirs)

    world = world or WorldState()
    ecosystem_rules = ecosystem_rules or EcosystemRules()
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
    belief_store = BeliefStore()
    resource_manager = resource_manager or ResourceManager()
    event_bus = event_bus or get_global_event_bus()
    value_weights = load_value_weights()
    governance_policy = governance_policy or MutationGovernancePolicy(value_weights=value_weights)
    register_memory_event_handlers(event_bus)
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
    intrinsic_goals = IntrinsicGoals(value_weights=value_weights)
    if coevolve_tests and test_pool is None:
        test_pool = LivingTestPool()

    with RunLogger(run_id, psyche=psyche) as logger:
        health_tracker = HealthTracker.from_state(state.health_counters)
        delayed: list[tuple[float, str, Path]] = []
        tick_count = 0
        while time.time() - start < budget_seconds:
            if max_iterations is not None and tick_count >= max_iterations:
                break
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
                tick_count += 1
                continue

            resource_manager.metabolize()
            signals = capture_signals(bus=event_bus)
            temp = get_temperature()
            signals["temperature"] = temp
            signals["skill_reputation"] = logger.skill_reputation()
            resource_manager.update_from_environment(temp)
            state.iteration += 1

            now = time.time()
            if delayed and delayed[0][0] <= now:
                _, org_name, skill_path = heapq.heappop(delayed)
                decision = Psyche.Decision.ACCEPT
            else:
                org_name, skill_path = _choose_skill(
                    rng,
                    world.organisms,
                    skill_reputation=logger.skill_reputation(),
                )
                decision = Psyche.Decision.ACCEPT
                if hasattr(psyche, "irrational_decision"):
                    decision = psyche.irrational_decision(rng)
            trigger_genesis, trigger_name, trigger_snapshot = _should_trigger_skill_genesis(
                signals=signals,
                health_counters=state.health_counters,
            )
            if trigger_genesis:
                mem_dir = Path(os.environ.get("SINGULAR_HOME", ".")) / "mem"
                genesis = create_skill(
                    skills_dir=world.organisms[org_name].skills_dir,
                    mem_dir=mem_dir,
                    governance_policy=governance_policy,
                    trigger=trigger_name,
                    signal_snapshot=trigger_snapshot,
                )
                logger.log_interaction(
                    "skill_genesis",
                    organism=org_name,
                    accepted=genesis.accepted,
                    skill=genesis.skill_name,
                    target=str(genesis.target),
                    policy_level=genesis.policy_level,
                    reason=genesis.reason,
                    rolled_back=genesis.rolled_back,
                    trigger=trigger_name,
                    trigger_snapshot=trigger_snapshot,
                    alive=True,
                )

            original = skill_path.read_text(encoding="utf-8")
            if not governance_policy.mutations_enabled():
                logger.log_interaction(
                    "mutation_halted",
                    organism=org_name,
                    target=str(skill_path),
                    severity="critical",
                    reason=governance_policy.mutation_lock_reason(),
                    alive=True,
                )
                continue

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
                governance_root = skill_path.parent.parent if skill_path.parent.name == "skills" else skill_path.parent
                decision = governance_policy.enforce_write(skill_path, mutated, root=governance_root)
                if not decision.allowed:
                    logger.log_interaction(
                        "governance_violation",
                        organism=org_name,
                        target=str(skill_path),
                        level=decision.level,
                        severity=decision.severity,
                        reason=decision.reason,
                        corrective_action=decision.corrective_action,
                        alive=True,
                    )
                    continue
                logger.log_absurde(skill_path.name, diff)
                continue

            policy = psyche.mutation_policy()
            last_health = (
                float(state.health_history[-1].get("score", 50.0))
                if state.health_history
                else 50.0
            )
            goal_weights = intrinsic_goals.update_tick(
                tick=state.iteration,
                psyche=psyche,
                health_score=last_health,
                resources={
                    "energy": resource_manager.energy,
                    "food": resource_manager.food,
                    "warmth": resource_manager.warmth,
                },
                perception_signals=signals,
            )
            baseline_failure_risk = (
                float(state.health_counters.get("sandbox_failures", 0))
                / max(float(state.health_counters.get("total", 0)), 1.0)
            )
            max_count = max((stats[name]["count"] for name in operators), default=0.0)
            candidate_names = list(operators.keys())
            rng.shuffle(candidate_names)
            candidate_names = candidate_names[: max(1, min(5, len(candidate_names)))]
            hypotheses: list[ActionHypothesis] = []
            for candidate in candidate_names:
                candidate_stats = stats[candidate]
                expected_gain = (
                    candidate_stats["reward"] / candidate_stats["count"]
                    if candidate_stats["count"]
                    else 0.0
                )
                long_term = 0.5 + max(-0.5, min(0.5, expected_gain))
                resource_cost = (
                    (candidate_stats["count"] / max_count) if max_count else 0.0
                )
                hypotheses.append(
                    ActionHypothesis(
                        action=candidate,
                        long_term=long_term,
                        sandbox_risk=baseline_failure_risk,
                        resource_cost=resource_cost,
                    )
                )
            adjusted_hypotheses = intrinsic_goals.influence_action_hypotheses(hypotheses)
            weighted_hypotheses = [
                ActionHypothesis(
                    action=entry["action"],
                    long_term=entry["long_term"],
                    sandbox_risk=entry["sandbox_risk"],
                    resource_cost=entry["resource_cost"],
                    metadata={"goal_weights": asdict(goal_weights)},
                )
                for entry in adjusted_hypotheses
            ]
            psyche_axes = getattr(psyche, "weighted_objective_axes", lambda: {})()
            reflection = reflect_action(
                weighted_hypotheses,
                bus=event_bus,
                event_context={"iteration": state.iteration, "organism": org_name},
                long_term_weight=(
                    goal_weights.coherence
                    + (psyche_axes.get("long_term", 0.0) * 0.4)
                ),
                sandbox_weight=(
                    goal_weights.robustesse
                    + (psyche_axes.get("sandbox", 0.0) * 0.4)
                ),
                resource_weight=(
                    goal_weights.efficacite
                    + (psyche_axes.get("resource", 0.0) * 0.4)
                ),
            )
            score_by_index = {index: score for index, _, score in reflection.alternative_scores}
            belief_bias = belief_store.operator_preference_bias(operators.keys())
            combined_bias = intrinsic_goals.influence_operator_scores(
                stats,
                skill_reputation=logger.skill_reputation(),
            )
            psyche_bias = getattr(psyche, "operator_bias", lambda names: {})(list(operators.keys()))
            for operator_name, extra_bias in belief_bias.items():
                combined_bias[operator_name] = combined_bias.get(operator_name, 0.0) + extra_bias
            for operator_name, extra_bias in psyche_bias.items():
                combined_bias[operator_name] = combined_bias.get(operator_name, 0.0) + extra_bias
            reputation_bonus = world.reputation.get(org_name) * 0.01
            for operator_name in combined_bias:
                combined_bias[operator_name] += reputation_bonus

            mood_label = getattr(getattr(psyche, "last_mood", None), "value", None)
            if mood_label is None and getattr(psyche, "last_mood", None) is not None:
                mood_label = str(getattr(psyche, "last_mood"))
            predicted_failure = (
                "hot"
                if temp >= 30.0
                else "cold"
                if temp <= 5.0
                else "stable"
            )
            meta_recommendation = None
            if policy != "analyze":
                meta_recommendation = recommend_strategy(
                    belief_store,
                    failure_type="anticipated",
                    environment_signal=predicted_failure,
                    mood=mood_label,
                    outcome_hint="success",
                    candidates=operators.keys(),
                )
            if policy == "analyze":
                op_name = select_operator(
                    operators,
                    stats,
                    policy,
                    rng,
                    objective_bias=combined_bias,
                )
            elif (
                reflection.action is None
                and meta_recommendation is not None
                and meta_recommendation.confidence >= 0.55
            ):
                op_name = meta_recommendation.operator
            else:
                op_name = reflection.action or select_operator(
                    operators,
                    stats,
                    policy,
                    rng,
                    objective_bias=combined_bias,
                )
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
            security_metadata: dict[str, object] = {
                "governance_checked": False,
                "allowed": accepted,
                "level": None,
                "reason": "score_gate",
                "corrective_action": None,
            }
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
            org.last_score = mutated_score
            if accepted:
                governance_root = skill_path.parent.parent if skill_path.parent.name == "skills" else skill_path.parent
                decision = governance_policy.enforce_write(skill_path, mutated, root=governance_root)
                security_metadata = {
                    "governance_checked": True,
                    "allowed": decision.allowed,
                    "level": decision.level,
                    "reason": decision.reason,
                    "corrective_action": decision.corrective_action,
                }
                if not decision.allowed:
                    accepted = False
                    logger.log_interaction(
                        "governance_violation",
                        organism=org_name,
                        target=str(skill_path),
                        level=decision.level,
                        severity=decision.severity,
                        reason=decision.reason,
                        corrective_action=decision.corrective_action,
                        alive=True,
                    )
                    org.energy -= 0.1
                else:
                    org.energy += 0.2
                    world.reputation.update(
                        org_name,
                        "share",
                        {"moral_weights": ecosystem_rules.reputation_action_weights},
                    )
                    env_artifacts.save_text(f"mutation_{state.iteration}", diff)
            else:
                org.energy -= 0.1
                world.reputation.update(
                    org_name,
                    "steal",
                    {"moral_weights": ecosystem_rules.reputation_action_weights},
                )

            objective_weights = asdict(goal_weights)
            dominant_objective = max(
                objective_weights,
                key=lambda objective_name: objective_weights[objective_name],
            )
            mood_value = getattr(getattr(psyche, "last_mood", None), "value", None)
            if mood_value is None:
                raw_mood = getattr(psyche, "last_mood", None)
                mood_value = str(raw_mood) if raw_mood is not None else None
            logger.log_consciousness(
                perception_summary=(
                    f"temp={temp:.2f}, baseline_failure_risk={baseline_failure_risk:.3f}, "
                    f"resource_energy={resource_manager.energy:.2f}"
                ),
                evaluated_hypotheses=[
                    {
                        "hypothesis_index": hypothesis_index,
                        "action": hypothesis.action,
                        "long_term": hypothesis.long_term,
                        "sandbox_risk": hypothesis.sandbox_risk,
                        "resource_cost": hypothesis.resource_cost,
                        "score": score_by_index.get(hypothesis_index),
                    }
                    for hypothesis_index, hypothesis in enumerate(weighted_hypotheses)
                ],
                final_choice=op_name,
                justification=reflection.decision_reason,
                objective=dominant_objective,
                mood=mood_value,
                energy=float(getattr(psyche, "energy", resource_manager.energy)),
                success=accepted,
            )

            stats[op_name]["count"] += 1
            reward_delta = base_score - mutated_score
            if math.isfinite(reward_delta):
                stats[op_name]["reward"] += reward_delta
            belief_store.update_after_run(
                f"operator:{op_name}",
                success=accepted,
                evidence=f"accepted={accepted};base={base_score:.6f};new={mutated_score:.6f}",
                reward_delta=reward_delta if math.isfinite(reward_delta) else 0.0,
            )
            run_features = extract_run_features(
                operator=op_name,
                accepted=accepted,
                base_score=base_score,
                mutated_score=mutated_score,
                temperature=temp,
                mood=mood_value,
            )
            register_run_result(
                belief_store,
                run_features,
                reward_delta=reward_delta if math.isfinite(reward_delta) else 0.0,
            )
            belief_store.forget_stale()
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

            # Shared world resources: cooperation and competition arbitration.
            competition_unit = max(ecosystem_rules.resource_competition_unit, 0.0)
            cooperation_partners: list[str] = []
            other_names = [name for name in world.organisms if name != org_name]
            arbitration_seed = int(
                hashlib.sha1(f"{state.iteration}:{org_name}".encode("utf-8")).hexdigest()[:8],
                16,
            )
            arbitration_rng = random.Random(arbitration_seed)
            if other_names and arbitration_rng.random() < max(
                ecosystem_rules.cooperation_probability, 0.0
            ):
                cooperation_partners.append(arbitration_rng.choice(other_names))
            competitor_intents: list[CompetitorIntent] = []
            for other_name in other_names:
                if other_name in cooperation_partners:
                    continue
                other_priority = int(
                    max(world.reputation.get(other_name), 0.0) * 10
                ) + arbitration_rng.randint(0, 2)
                competitor_intents.append(
                    CompetitorIntent(
                        life_id=other_name,
                        priority=other_priority,
                        bid=arbitration_rng.uniform(
                            0.0, ecosystem_rules.competition_bid_ceiling
                        ),
                    )
                )
            action_resolution = world.world_resources.consume_for_action(
                life_id=org_name,
                cpu_cost=max(cpu_ms / 1000.0, 0.05),
                mutation_cost=max(competition_unit, 0.05),
                attention_cost=1.0 if accepted else 1.2,
                cooperation_partners=cooperation_partners,
                priority=int(max(world.reputation.get(org_name), 0.0) * 10),
                bid=arbitration_rng.uniform(0.0, ecosystem_rules.competition_bid_ceiling),
                competitor_intents=competitor_intents,
            )
            if action_resolution.granted:
                world.resource_pool = max(
                    0.0,
                    world.resource_pool
                    - max(
                        action_resolution.consumed["mutation_slots"],
                        competition_unit,
                    ),
                )
                org.resources = max(
                    0.0,
                    org.resources
                    + competition_unit
                    - (action_resolution.consumed["cpu_budget"] * 0.01)
                    - (action_resolution.consumed["attention_score"] * 0.01),
                )
            else:
                org.resources = max(
                    0.0,
                    org.resources - (competition_unit * 0.2) - action_resolution.rivalry_penalty,
                )

            if cooperation_partners:
                for partner in cooperation_partners:
                    world.reputation.update(partner, "share")
                world.reputation.update(org_name, "share")
                org.energy += action_resolution.relation_bonus
            elif action_resolution.conflicts:
                world.reputation.update(org_name, "steal")

            for other in world.organisms.values():
                other.energy = max(0.1, other.energy - ecosystem_rules.passive_energy_decay)
                other.resources = max(
                    0.1,
                    other.resources - ecosystem_rules.passive_resource_decay,
                )

            sandbox_failure = (
                base_score == float("-inf") or mutated_score == float("-inf")
            )
            if sandbox_failure:
                governance_policy.record_violation(
                    category="sandbox_violation",
                    severity="critical",
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
            state.health_history = _retain_health_history(state.health_history)
            state.health_counters = health_tracker.to_state()

            logger.log_interaction(
                INTERACTION_RESOURCE_COMPETITION,
                organism=org_name,
                resource_pool=world.resource_pool,
                world_resources={
                    "cpu_budget": world.world_resources.cpu_budget,
                    "mutation_slots": world.world_resources.mutation_slots,
                    "attention_score": world.world_resources.attention_score,
                },
                contention=action_resolution.contention,
                conflicts=action_resolution.conflicts,
                arbitration_winner=action_resolution.arbitration_winner,
                cooperation_partners=action_resolution.cooperation_partners,
                energy=org.energy,
                resources=org.resources,
                reputation=world.reputation.get(org_name),
                score=org.last_score,
                alive=True,
            )

            key = (
                f"{org_name}:{skill_path.stem}"
                if len(world.organisms) > 1
                else skill_path.stem
            )
            update_score(key, mutated_score)
            mutation_payload = {
                "iteration": state.iteration,
                "skill": key,
                "op": op_name,
                "accepted": accepted,
                "score_base": base_score,
                "score_new": mutated_score,
                "loop_modifications": loop_modifications,
                "decision_reason": reflection.decision_reason,
                "alternative_scores": reflection.alternative_scores,
                "health": health_snapshot.to_dict(),
                "diff": diff,
                "impacted_file": skill_path.name,
                "timing_ms": {"base": ms_base, "new": ms_new},
                "skill_reputation": logger.skill_reputation().get(key, {}),
            }
            event_bus.publish(
                "mutation.applied" if accepted else "mutation.rejected",
                mutation_payload,
                payload_version=1,
            )
            life_root = Path(os.environ.get("SINGULAR_HOME", ".")).resolve()
            try:
                skill_relative_path = str(skill_path.resolve().relative_to(life_root))
            except ValueError:
                skill_relative_path = str(skill_path)

            record_generation(
                run_id=logger.run_id,
                iteration=state.iteration,
                skill=key,
                operator=op_name,
                mutation_diff=diff,
                score_base=base_score,
                score_new=mutated_score,
                accepted=accepted,
                reason=reflection.decision_reason,
                parent_hash=hashlib.sha256(original.encode("utf-8")).hexdigest(),
                candidate_code=mutated,
                skill_relative_path=skill_relative_path,
                security_metadata=security_metadata,
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
                alternative_scores=reflection.alternative_scores,
                decision_reason=reflection.decision_reason,
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
                org.energy = max(org.energy, 1.0)
                org.resources = max(org.resources, 1.0)
                org.monitor = DeathMonitor()
                tick_count += 1
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
                world.organisms[name].energy = 1.0
                world.organisms[name].resources = 1.0

            # Periodic crossover
            if (
                ecosystem_rules.crossover_interval > 0
                and state.iteration % ecosystem_rules.crossover_interval == 0
                and len(world.organisms) >= 2
            ):
                parent_names = list(_pick_crossover_parents(rng, world))
                pa = world.organisms[parent_names[0]].skills_dir
                pb = world.organisms[parent_names[1]].skills_dir
                child_dir = pa.parent / f"child_{state.iteration}"
                child_skills_dir = child_dir / "skills"
                child_skills_dir.mkdir(parents=True, exist_ok=True)
                fname, code = crossover(pa, pb, rng)
                target = child_skills_dir / fname
                authorized, reason = authorize_reproduction_write(
                    target,
                    code,
                    governance_policy=governance_policy,
                )
                if not authorized:
                    logger.log_interaction(
                        "governance_violation",
                        parents=parent_names,
                        target=str(target),
                        reason=reason,
                        corrective_action="write under allowlisted skills/ directory",
                        alive=True,
                    )
                else:
                    world.organisms[child_dir.name] = Organism(child_skills_dir)
                    logger.log_interaction(
                        INTERACTION_CROSSOVER,
                        parents=parent_names,
                        child=child_dir.name,
                        child_skills_dir=str(child_dir),
                        alive=True,
                    )
            tick_count += 1

    for org in world.organisms.values():
        if org.last_score != float("-inf"):
            continue
        skill_files = sorted(org.skills_dir.glob("*.py"))
        if not skill_files:
            continue
        try:
            source = skill_files[0].read_text(encoding="utf-8")
        except OSError:
            continue
        fallback_score = score_code(source)
        if fallback_score == float("-inf") and "=" in source:
            try:
                fallback_score = float(source.split("=", maxsplit=1)[1].strip())
            except (TypeError, ValueError):
                fallback_score = 0.0
        org.last_score = fallback_score
    return state


def run_tick(
    skills_dirs: OrganismInputs,
    checkpoint_path: Path,
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
    event_bus: EventBus | None = None,
    governance_policy: MutationGovernancePolicy | None = None,
    tick_budget_seconds: float = 0.2,
    ecosystem_rules: EcosystemRules | None = None,
) -> Checkpoint:
    """Execute one mutation tick and persist checkpoint state."""

    return run(
        skills_dirs=skills_dirs,
        checkpoint_path=checkpoint_path,
        budget_seconds=max(tick_budget_seconds, 0.01),
        rng=rng,
        run_id=run_id,
        operators=operators,
        mortality=mortality,
        world=world,
        map_elites=map_elites,
        resource_manager=resource_manager,
        test_runner=test_runner,
        coevolve_tests=coevolve_tests,
        test_pool=test_pool,
        robustness_weight=robustness_weight,
        max_test_candidates=max_test_candidates,
        event_bus=event_bus,
        governance_policy=governance_policy,
        max_iterations=1,
        ecosystem_rules=ecosystem_rules,
    )


def main(argv: list[str] | None = None) -> None:  # pragma: no cover - CLI wrapper
    parser = argparse.ArgumentParser(description="evolutionary life loop")
    parser.add_argument("--skills-dir", type=Path, default=Path("skills"))
    parser.add_argument("--checkpoint", type=Path, default=Path("life_checkpoint.json"))
    parser.add_argument("--budget-seconds", type=float, required=True)
    args = parser.parse_args(argv)

    run(args.skills_dir, args.checkpoint, args.budget_seconds)


if __name__ == "__main__":  # pragma: no cover - module executable
    main()
