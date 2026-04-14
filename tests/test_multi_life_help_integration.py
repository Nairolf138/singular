from pathlib import Path

from singular.events import EventBus
from singular.governance.policy import AUTH_AUTO, MutationGovernancePolicy
from singular.multiagent import (
    CollectiveMemory,
    HelpExchangeCoordinator,
    InMemoryQueueTransport,
)


def test_multi_life_help_improves_success_without_policy_violation(tmp_path: Path) -> None:
    requester_root = tmp_path / "life-a"
    helper_root = tmp_path / "life-b"
    requester_skills = requester_root / "skills"
    helper_skills = helper_root / "skills"
    requester_skills.mkdir(parents=True)
    helper_skills.mkdir(parents=True)
    (helper_skills / "solve_task.py").write_text(
        "def run(context):\n    return context.get('value', 0)\n",
        encoding="utf-8",
    )

    policy = MutationGovernancePolicy(
        modifiable_paths=("skills",),
        review_required_paths=(),
        forbidden_paths=("src", ".git", "mem", "runs", "tests"),
    )
    transport = InMemoryQueueTransport()
    memory = CollectiveMemory(tmp_path / "collective", "help")
    coordinator = HelpExchangeCoordinator(
        transport=transport,
        policy=policy,
        bus=EventBus(),
        memory=memory,
        success_window=10,
    )

    for _ in range(5):
        coordinator.register_outcome(life_id="life-a", task="task-x", success=False)
    for _ in range(5):
        coordinator.register_outcome(life_id="life-b", task="task-x", success=True)

    before = coordinator.success_rate(life_id="life-a", task="task-x")
    result = coordinator.transfer_skill(
        requester_life="life-a",
        helper_life="life-b",
        task="task-x",
        helper_skill_path=helper_skills / "solve_task.py",
        requester_skills_dir=requester_skills,
    )
    after = coordinator.success_rate(life_id="life-a", task="task-x")

    assert before == 0.0
    assert after > before
    assert result.status == "completed"
    assert result.decision == AUTH_AUTO
    assert result.requester_gain > 0.0
    assert result.helper_gain >= 0.0
    assert (requester_skills / "solve_task.py").exists()

    sent = transport.receive()
    intents = [message.intent for message in sent]
    assert "help.offered" in intents
    assert "help.accepted" in intents
    assert "help.completed" in intents

    records = memory.read()
    assert records
    assert records[0]["kind"] == "help_transfer"
    assert records[0]["requester_gain"] > 0.0
