from __future__ import annotations

import ast
import json
import random
from dataclasses import dataclass
from pathlib import Path

import pytest

from singular.cognition.reflect import ActionHypothesis, reflect_action
from singular.life import loop
from singular.life.coevolution_flow import CoevolutionConfig, CoevolutionFlow, LivingTestPool, TestCandidate
from singular.life.loop import EcosystemRules, Organism, WorldState, run_tick
from singular.life.mutation_flow import select_operator
from singular.life.reproduction_flow import ReproductionDecisionPolicy, decide_reproduction
from singular.life.sandbox_scoring import score_code_with_error
from singular.resource_manager import ResourceManager


def _dec_operator(tree: ast.AST, rng=None) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            node.value -= 1
            break
    return tree


def _inc_operator(tree: ast.AST, rng=None) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            node.value += 1
            break
    return tree


def test_reflection_prefers_long_term_low_risk_action() -> None:
    decision = reflect_action(
        [
            ActionHypothesis("risky", long_term=0.9, sandbox_risk=0.9, resource_cost=0.7),
            ActionHypothesis("steady", long_term=0.75, sandbox_risk=0.05, resource_cost=0.05),
        ]
    )

    assert decision.action == "steady"
    assert decision.ranked_actions[0] == "steady"
    assert decision.assessments[0].action_recommended == "execute"


def test_operator_selection_uses_analyze_and_objective_bias() -> None:
    operators = {"low_count": _dec_operator, "rewarded": _inc_operator}
    stats = {"low_count": {"count": 0, "reward": 0.0}, "rewarded": {"count": 3, "reward": 1.0}}

    assert select_operator(operators, stats, "analyze", random.Random(0)) == "low_count"

    stats["low_count"]["count"] = 3
    assert (
        select_operator(
            operators,
            stats,
            "exploit",
            random.Random(0),
            objective_bias={"low_count": 2.0},
        )
        == "low_count"
    )


def test_sandbox_scoring_reports_success_and_failure() -> None:
    ok = score_code_with_error("result = 1\n")
    bad = score_code_with_error("raise RuntimeError('boom')\n")

    assert ok.ok is True
    assert ok.score == 1.0
    assert bad.ok is False
    assert bad.score == float("-inf")
    assert bad.error_type is not None


def test_run_tick_manages_resources_and_mutates_skill(temp_life) -> None:
    resources = ResourceManager(path=temp_life["root"] / "resources.json")
    before_energy = resources.energy

    state = run_tick(
        temp_life["skills_dir"],
        temp_life["checkpoint_path"],
        rng=random.Random(0),
        operators={"dec": _dec_operator},
        resource_manager=resources,
        ecosystem_rules=EcosystemRules(crossover_interval=0),
        tick_budget_seconds=0.05,
    )

    assert state.iteration == 1
    assert (temp_life["skills_dir"] / "skill.py").read_text(encoding="utf-8").strip() == "result = 1"
    assert resources.energy != before_energy


@dataclass
class _SleepyPsyche:
    energy: float = 1.0
    sleeping: bool = False
    mutation_rate: float = 1.0
    sleep_ticks: int = 0

    def sleep_tick(self) -> None:
        self.sleep_ticks += 1
        self.energy += 1.0

    def save_state(self) -> None:  # pragma: no cover - no-op test double
        return None


def test_run_tick_sleeps_without_mutating_when_energy_is_low(temp_life, monkeypatch: pytest.MonkeyPatch) -> None:
    sleepy = _SleepyPsyche()
    monkeypatch.setattr(loop.Psyche, "load_state", staticmethod(lambda: sleepy))

    state = run_tick(
        temp_life["skills_dir"],
        temp_life["checkpoint_path"],
        rng=random.Random(0),
        operators={"dec": _dec_operator},
        tick_budget_seconds=0.05,
    )

    assert state.iteration == 0
    assert sleepy.sleeping is True
    assert sleepy.sleep_ticks == 1
    assert (temp_life["skills_dir"] / "skill.py").read_text(encoding="utf-8") == "result = 2\n"


def test_reproduction_decision_accepts_healthy_governed_parents(temp_life) -> None:
    parent_a = temp_life["root"] / "a" / "skills"
    parent_b = temp_life["root"] / "b" / "skills"
    parent_a.mkdir(parents=True)
    parent_b.mkdir(parents=True)
    (parent_a / "a.py").write_text("result = 1\n", encoding="utf-8")
    (parent_b / "b.py").write_text("result = 1\n", encoding="utf-8")

    decision = decide_reproduction(
        parent_a="a",
        parent_b="b",
        parent_a_skills=parent_a,
        parent_b_skills=parent_b,
        parent_a_health=1.0,
        parent_b_health=1.0,
        governance_allowed=True,
        policy=ReproductionDecisionPolicy(min_parent_health=0.1, compatibility_threshold=0.1),
    )

    assert decision.accepted is True
    assert decision.score >= 0.1


def test_coevolution_rejects_regression_detected_by_living_test() -> None:
    flow = CoevolutionFlow(
        pool=LivingTestPool(tests=[TestCandidate("result == 1")], ttl={"result == 1": 3}),
        config=CoevolutionConfig(enabled=True, robustness_weight=1.0),
    )

    decision = flow.decide(
        base_code="result = 1",
        mutated_code="result = 2",
        base_score=1.0,
        mutated_score=1.0,
        initially_accepted=True,
        rng=random.Random(0),
    )

    assert decision.accepted is False
    assert decision.rejected_for_robustness is True
    assert decision.regression_detection_rate == 1.0


def test_cycle_complet_creation_tick_mutation_learning_reproduction_and_stop(temp_life) -> None:
    world = WorldState(
        organisms={
            "alpha": Organism(temp_life["skills_dir"], energy=5.0, resources=5.0),
            "beta": Organism(temp_life["root"] / "beta" / "skills", energy=5.0, resources=5.0),
        }
    )
    (temp_life["skills_dir"] / "skill.py").write_text("result = 2\ndef solve():\n    return 2\n", encoding="utf-8")
    beta_skill = world.organisms["beta"].skills_dir
    beta_skill.mkdir(parents=True)
    (beta_skill / "skill.py").write_text("result = 3\ndef solve():\n    return 3\n", encoding="utf-8")

    state = run_tick(
        {name: org.skills_dir for name, org in world.organisms.items()},
        temp_life["checkpoint_path"],
        rng=random.Random(1),
        operators={"dec": _dec_operator},
        world=world,
        ecosystem_rules=EcosystemRules(
            crossover_interval=1,
            reproduction_policy=ReproductionDecisionPolicy(min_parent_health=0.1, compatibility_threshold=0.1, cooldown_ticks=1),
        ),
        tick_budget_seconds=0.05,
    )

    assert state.iteration == 1
    assert state.stats["dec"]["count"] == 1
    assert list(Path("runs").glob("**/*.jsonl"))
    assert any(path.name.startswith("child_") for path in temp_life["root"].iterdir()) or world.reproduction_cooldowns

    stopped = loop.run(
        temp_life["skills_dir"],
        temp_life["checkpoint_path"],
        budget_seconds=0.0,
        rng=random.Random(2),
        operators={"dec": _dec_operator},
        max_iterations=0,
    )
    assert stopped.iteration == state.iteration
