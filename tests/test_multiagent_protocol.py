from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import multiprocessing as mp
from pathlib import Path

from singular.multiagent import (
    AgentMessage,
    CollectiveMemory,
    FileQueueTransport,
    InMemoryQueueTransport,
    OrchestrationScenario,
    resolve_conflicts,
)


def _send_messages_worker(path: str, start: int, count: int) -> None:
    transport = FileQueueTransport(Path(path))
    for idx in range(start, start + count):
        transport.send(
            AgentMessage(
                intent="answer",
                task=f"part-{idx}",
                evidence=["mp"],
                confidence=0.9,
            )
        )


def _append_collective_worker(root: str, namespace: str, start: int, count: int) -> None:
    memory = CollectiveMemory(Path(root), namespace)
    for idx in range(start, start + count):
        memory.append({"kind": "mp", "id": idx})


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


def test_file_queue_transport_concurrent_threads_and_processes(tmp_path):
    queue_path = tmp_path / "queue" / "messages.jsonl"
    transport = FileQueueTransport(queue_path)
    thread_count = 40
    with ThreadPoolExecutor(max_workers=8) as pool:
        for idx in range(thread_count):
            pool.submit(
                transport.send,
                AgentMessage(
                    intent="answer",
                    task=f"thread-{idx}",
                    evidence=["thread"],
                    confidence=0.7,
                ),
            )

    processes = [
        mp.Process(
            target=_send_messages_worker,
            args=(str(queue_path), proc_idx * 15, 15),
        )
        for proc_idx in range(2)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=10)
        assert process.exitcode == 0

    lines = queue_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == thread_count + 30
    assert all(line.strip() for line in lines)
    parsed = [json.loads(line) for line in lines]
    assert len(parsed) == thread_count + 30


def test_collective_memory_concurrent_threads_and_processes(tmp_path):
    root = tmp_path / "collective"
    memory = CollectiveMemory(root, "alpha")
    thread_count = 30
    with ThreadPoolExecutor(max_workers=6) as pool:
        for idx in range(thread_count):
            pool.submit(memory.append, {"kind": "thread", "id": idx})

    processes = [
        mp.Process(
            target=_append_collective_worker,
            args=(str(root), "alpha", proc_idx * 10, 10),
        )
        for proc_idx in range(2)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=10)
        assert process.exitcode == 0

    records = memory.read()
    assert len(records) == thread_count + 20
    ids = {record["id"] for record in records}
    assert set(range(thread_count)).issubset(ids)
