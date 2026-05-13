"""Executable demo: two lives exchange a skill and resolve an offer conflict.

Run from the repository root:
    PYTHONPATH=src python examples/multiagent_life_loop/demo.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from singular.governance.policy import MutationGovernancePolicy
from singular.multiagent import (
    CollectiveMemory,
    InMemoryQueueTransport,
    LifeTickContext,
    MultiAgentPolicy,
    MultiAgentRuntime,
    TaskOffer,
)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="singular-multiagent-demo-") as tmp:
        root = Path(tmp)
        alpha_skills = root / "alpha" / "skills"
        beta_skills = root / "beta" / "skills"
        alpha_skills.mkdir(parents=True)
        beta_skills.mkdir(parents=True)
        alpha_skill = alpha_skills / "rough_solver.py"
        beta_skill = beta_skills / "expert_solver.py"
        alpha_skill.write_text("result = 10\n", encoding="utf-8")
        beta_skill.write_text("result = -3\n", encoding="utf-8")

        transport = InMemoryQueueTransport()
        runtime = MultiAgentRuntime(
            transport=transport,
            policy=MultiAgentPolicy(low_score_threshold=0.0, high_confidence_threshold=0.8),
            governance_policy=MutationGovernancePolicy(
                modifiable_paths=("skills",),
                review_required_paths=(),
                forbidden_paths=("src", ".git", "mem", "runs", "tests"),
            ),
            memory=CollectiveMemory(root / "collective", "demo"),
        )

        beta_context = LifeTickContext(
            life_id="beta",
            task="shared:solver",
            skill_path=beta_skill,
            skills_dir=beta_skills,
            score=-3.0,
            confidence=0.95,
            governance_allowed=True,
            peers=("alpha",),
            iteration=1,
        )
        beta_decision = runtime.begin_tick(beta_context)
        print("beta emitted:", [message.intent for message in beta_decision.emitted])

        # A second, lower-priority offer creates a conflict. Alpha resolves the
        # conflict by accepting beta's higher-priority/high-confidence offer.
        runtime.emit(
            TaskOffer(
                helper_id="gamma",
                receiver_id="alpha",
                task="shared:solver",
                skill="noisy_solver.py",
                confidence=0.45,
                priority=1,
                evidence=["lower_priority_demo_offer"],
            ).to_message()
        )
        alpha_context = LifeTickContext(
            life_id="alpha",
            task="shared:solver",
            skill_path=alpha_skill,
            skills_dir=alpha_skills,
            score=5.0,
            confidence=0.2,
            governance_allowed=True,
            peers=("beta",),
            iteration=2,
        )
        alpha_decision = runtime.begin_tick(alpha_context)
        print("alpha reasons:", alpha_decision.reasons)
        print("accepted offer:", alpha_decision.accepted_offer.skill if alpha_decision.accepted_offer else None)

        runtime.complete_tick(alpha_context, accepted=True, score_before=5.0, score_after=-3.0)
        print("collective records:", len(runtime.memory.read()) if runtime.memory else 0)


if __name__ == "__main__":
    main()
