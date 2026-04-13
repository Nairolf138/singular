from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Protocol
import json
import tempfile
import time
from collections import defaultdict, deque


@dataclass(slots=True)
class AgentMessage:
    """Versioned multi-agent message format.

    Version 1 keeps the required fields explicit:
    ``intent``, ``task``, ``evidence`` and ``confidence``.
    """

    intent: str
    task: str
    evidence: list[str]
    confidence: float
    priority: int = 0
    agent_id: str | None = None
    version: int = 1
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.version != 1:
            raise ValueError("unsupported message version")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "intent": self.intent,
            "task": self.task,
            "evidence": list(self.evidence),
            "confidence": self.confidence,
            "priority": self.priority,
            "agent_id": self.agent_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AgentMessage":
        return cls(
            version=int(payload.get("version", 1)),
            intent=str(payload["intent"]),
            task=str(payload["task"]),
            evidence=[str(item) for item in payload.get("evidence", [])],
            confidence=float(payload["confidence"]),
            priority=int(payload.get("priority", 0)),
            agent_id=(
                str(payload["agent_id"])
                if payload.get("agent_id") is not None
                else None
            ),
            created_at=float(payload.get("created_at", time.time())),
        )


class MessageTransport(Protocol):
    def send(self, message: AgentMessage) -> None: ...

    def receive(self) -> list[AgentMessage]: ...


class InMemoryQueueTransport:
    """Simple local transport backed by an in-memory queue."""

    def __init__(self) -> None:
        self._queue: deque[AgentMessage] = deque()

    def send(self, message: AgentMessage) -> None:
        self._queue.append(message)

    def receive(self) -> list[AgentMessage]:
        messages = list(self._queue)
        self._queue.clear()
        return messages


class FileQueueTransport:
    """Simple local transport backed by a JSONL file queue."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def send(self, message: AgentMessage) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(message.to_dict(), ensure_ascii=False) + "\n"
        existing = self.path.read_text(encoding="utf-8") if self.path.exists() else ""
        _atomic_write_text(self.path, existing + line)

    def receive(self) -> list[AgentMessage]:
        if not self.path.exists():
            return []
        payload = self.path.read_text(encoding="utf-8")
        _atomic_write_text(self.path, "")
        messages: list[AgentMessage] = []
        for line in payload.splitlines():
            if not line.strip():
                continue
            messages.append(AgentMessage.from_dict(json.loads(line)))
        return messages


def resolve_conflicts(messages: Iterable[AgentMessage]) -> dict[str, AgentMessage]:
    """Pick one message per task using priority then confidence."""

    grouped: dict[str, list[AgentMessage]] = defaultdict(list)
    for message in messages:
        grouped[message.task].append(message)

    resolved: dict[str, AgentMessage] = {}
    for task, candidates in grouped.items():
        resolved[task] = sorted(
            candidates,
            key=lambda msg: (-msg.priority, -msg.confidence, msg.created_at),
        )[0]
    return resolved


class CollectiveMemory:
    """Optional shared memory, isolated by namespace."""

    def __init__(self, root: Path | str, namespace: str) -> None:
        self.root = Path(root)
        self.namespace = namespace

    @property
    def _path(self) -> Path:
        return self.root / f"{self.namespace}.jsonl"

    def append(self, record: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False) + "\n"
        existing = self._path.read_text(encoding="utf-8") if self._path.exists() else ""
        _atomic_write_text(self._path, existing + line)

    def read(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        out: list[dict[str, Any]] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
        return out


@dataclass(slots=True)
class OrchestrationScenario:
    """Scenario helper for distributing sub-problems and merging outcomes."""

    transport: MessageTransport
    memory: CollectiveMemory | None = None

    def share_subproblems(
        self,
        parent_task: str,
        subproblems: dict[str, str],
    ) -> list[AgentMessage]:
        sent: list[AgentMessage] = []
        for agent_id, task in subproblems.items():
            message = AgentMessage(
                intent="sub_problem",
                task=task,
                evidence=[f"parent:{parent_task}"],
                confidence=1.0,
                priority=0,
                agent_id=agent_id,
            )
            self.transport.send(message)
            if self.memory is not None:
                self.memory.append(
                    {
                        "kind": "dispatch",
                        "agent_id": agent_id,
                        "task": task,
                        "parent_task": parent_task,
                    }
                )
            sent.append(message)
        return sent

    def merge_results(self, results: Iterable[AgentMessage]) -> dict[str, Any]:
        winners = resolve_conflicts(results)
        merged = {
            "tasks": {
                task: {
                    "intent": msg.intent,
                    "agent_id": msg.agent_id,
                    "confidence": msg.confidence,
                    "priority": msg.priority,
                    "evidence": msg.evidence,
                }
                for task, msg in winners.items()
            },
            "evidence": [
                evidence
                for message in winners.values()
                for evidence in message.evidence
            ],
        }
        if self.memory is not None:
            self.memory.append({"kind": "merge", "payload": merged})
        return merged


def _atomic_write_text(path: Path, data: str) -> None:
    tmp = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    )
    try:
        with tmp:
            tmp.write(data)
            tmp.flush()
        Path(tmp.name).replace(path)
    finally:
        try:
            Path(tmp.name).unlink()
        except FileNotFoundError:
            pass
