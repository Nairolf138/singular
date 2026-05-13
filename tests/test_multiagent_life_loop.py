from __future__ import annotations

import ast
import random
from pathlib import Path

from singular.governance.policy import MutationGovernancePolicy
from singular.life.loop import EcosystemRules, WorldState, run_tick
from singular.multiagent import (
    InMemoryQueueTransport,
    LifeTickContext,
    MultiAgentPolicy,
    MultiAgentRuntime,
    TaskOffer,
)


def _dec_operator(tree: ast.AST, rng=None) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            node.value -= 1
            break
    return tree


def _governance_policy() -> MutationGovernancePolicy:
    return MutationGovernancePolicy(
        modifiable_paths=("skills",),
        review_required_paths=(),
        forbidden_paths=("src", ".git", "mem", "runs", "tests"),
    )


def test_runtime_requests_help_offers_skill_and_resolves_offer_conflict(tmp_path: Path) -> None:
    transport = InMemoryQueueTransport()
    runtime = MultiAgentRuntime(
        transport=transport,
        policy=MultiAgentPolicy(low_score_threshold=0.0, high_confidence_threshold=0.8),
        governance_policy=_governance_policy(),
    )
    alpha_skills = tmp_path / "alpha" / "skills"
    beta_skills = tmp_path / "beta" / "skills"
    alpha_skills.mkdir(parents=True)
    beta_skills.mkdir(parents=True)
    alpha_skill = alpha_skills / "solver.py"
    beta_skill = beta_skills / "expert.py"
    alpha_skill.write_text("result = 4\n", encoding="utf-8")
    beta_skill.write_text("result = -1\n", encoding="utf-8")

    beta_decision = runtime.begin_tick(
        LifeTickContext(
            life_id="beta",
            task="shared:solver",
            skill_path=beta_skill,
            skills_dir=beta_skills,
            score=-1.0,
            confidence=0.95,
            governance_allowed=True,
            peers=("alpha",),
        )
    )
    assert [message.intent for message in beta_decision.emitted] == ["help.requested", "help.offered"]

    runtime.emit(
        TaskOffer(
            helper_id="gamma",
            receiver_id="alpha",
            task="shared:solver",
            skill="weaker.py",
            confidence=0.2,
            priority=1,
        ).to_message()
    )
    alpha_decision = runtime.begin_tick(
        LifeTickContext(
            life_id="alpha",
            task="shared:solver",
            skill_path=alpha_skill,
            skills_dir=alpha_skills,
            score=3.0,
            confidence=0.1,
            governance_allowed=True,
            peers=("beta",),
        )
    )

    assert alpha_decision.accepted_offer is not None
    assert alpha_decision.accepted_offer.helper_id == "beta"
    assert alpha_decision.accepted_offer.skill == "expert.py"
    assert "accepted_best_offer" in alpha_decision.reasons


def test_runtime_refuses_and_gates_when_governance_or_rivalry_is_high(tmp_path: Path) -> None:
    transport = InMemoryQueueTransport()
    runtime = MultiAgentRuntime(transport=transport)
    skills_dir = tmp_path / "alpha" / "skills"
    skills_dir.mkdir(parents=True)
    skill = skills_dir / "solver.py"
    skill.write_text("result = 1\n", encoding="utf-8")

    decision = runtime.begin_tick(
        LifeTickContext(
            life_id="alpha",
            task="blocked:solver",
            skill_path=skill,
            skills_dir=skills_dir,
            score=1.0,
            confidence=0.9,
            governance_allowed=False,
            rivalry=0.9,
        )
    )

    assert decision.mutation_allowed is False
    assert decision.action_allowed is False
    assert decision.reproduction_allowed is False
    assert [message.intent for message in decision.emitted] == ["help.refused"]


def test_life_loop_consults_multiagent_runtime_during_tick(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))
    alpha_skills = tmp_path / "alpha" / "skills"
    beta_skills = tmp_path / "beta" / "skills"
    alpha_skills.mkdir(parents=True)
    beta_skills.mkdir(parents=True)
    (alpha_skills / "solver.py").write_text("result = 2\n", encoding="utf-8")
    (beta_skills / "helper.py").write_text("result = -2\n", encoding="utf-8")

    transport = InMemoryQueueTransport()
    runtime = MultiAgentRuntime(
        transport=transport,
        policy=MultiAgentPolicy(low_score_threshold=1.0, high_confidence_threshold=0.99),
        governance_policy=_governance_policy(),
    )
    world = WorldState()

    state = run_tick(
        {"alpha": alpha_skills, "beta": beta_skills},
        tmp_path / "checkpoint.json",
        rng=random.Random(0),
        operators={"dec": _dec_operator},
        world=world,
        governance_policy=_governance_policy(),
        multiagent_runtime=runtime,
        ecosystem_rules=EcosystemRules(crossover_interval=0),
        tick_budget_seconds=0.05,
    )

    assert state.iteration == 1
    intents = [message.intent for message in runtime.outbox]
    assert "help.requested" in intents
    assert any(intent in {"help.completed", "answer"} for intent in intents)
