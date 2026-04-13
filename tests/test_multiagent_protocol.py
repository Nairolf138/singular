from __future__ import annotations

from singular.multiagent import (
    AgentMessage,
    CollectiveMemory,
    FileQueueTransport,
    InMemoryQueueTransport,
    OrchestrationScenario,
    resolve_conflicts,
)


def test_message_is_versioned_and_serializable():
    message = AgentMessage(
        intent="answer",
        task="sum",
        evidence=["calc:1+1=2"],
        confidence=0.9,
        priority=1,
        agent_id="agent-a",
    )

    decoded = AgentMessage.from_dict(message.to_dict())
    assert decoded.version == 1
    assert decoded.intent == "answer"
    assert decoded.task == "sum"
    assert decoded.evidence == ["calc:1+1=2"]


def test_transports_queue_and_file(tmp_path):
    message = AgentMessage(
        intent="answer",
        task="part-a",
        evidence=["ok"],
        confidence=0.7,
    )

    memory_transport = InMemoryQueueTransport()
    memory_transport.send(message)
    assert [m.task for m in memory_transport.receive()] == ["part-a"]
    assert memory_transport.receive() == []

    file_transport = FileQueueTransport(tmp_path / "queue" / "messages.jsonl")
    file_transport.send(message)
    received = file_transport.receive()
    assert len(received) == 1
    assert received[0].task == "part-a"
    assert file_transport.receive() == []


def test_conflict_resolution_by_priority_then_confidence():
    messages = [
        AgentMessage(
            intent="answer",
            task="part-a",
            evidence=["low priority"],
            confidence=0.95,
            priority=1,
            agent_id="agent-a",
        ),
        AgentMessage(
            intent="answer",
            task="part-a",
            evidence=["high priority"],
            confidence=0.6,
            priority=2,
            agent_id="agent-b",
        ),
        AgentMessage(
            intent="answer",
            task="part-b",
            evidence=["best confidence"],
            confidence=0.8,
            priority=1,
            agent_id="agent-c",
        ),
    ]

    resolved = resolve_conflicts(messages)
    assert resolved["part-a"].agent_id == "agent-b"
    assert resolved["part-b"].agent_id == "agent-c"


def test_orchestration_sharing_merge_and_namespaced_memory(tmp_path):
    transport = InMemoryQueueTransport()
    alpha_memory = CollectiveMemory(tmp_path / "collective", "alpha")
    beta_memory = CollectiveMemory(tmp_path / "collective", "beta")

    scenario = OrchestrationScenario(transport=transport, memory=alpha_memory)
    scenario.share_subproblems(
        parent_task="global-problem",
        subproblems={"agent-a": "part-a", "agent-b": "part-b"},
    )

    dispatched = transport.receive()
    assert {message.task for message in dispatched} == {"part-a", "part-b"}

    merged = scenario.merge_results(
        [
            AgentMessage(
                intent="answer",
                task="part-a",
                evidence=["result-a"],
                confidence=0.7,
                priority=1,
                agent_id="agent-a",
            ),
            AgentMessage(
                intent="answer",
                task="part-a",
                evidence=["result-a-alt"],
                confidence=0.9,
                priority=1,
                agent_id="agent-c",
            ),
            AgentMessage(
                intent="answer",
                task="part-b",
                evidence=["result-b"],
                confidence=0.8,
                priority=1,
                agent_id="agent-b",
            ),
        ]
    )

    assert merged["tasks"]["part-a"]["agent_id"] == "agent-c"
    assert merged["tasks"]["part-b"]["agent_id"] == "agent-b"
    assert "result-b" in merged["evidence"]

    alpha_records = alpha_memory.read()
    assert any(record["kind"] == "dispatch" for record in alpha_records)
    assert any(record["kind"] == "merge" for record in alpha_records)
    assert beta_memory.read() == []
