from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal, Protocol
import json
import time
from collections import defaultdict, deque

from singular.events import (
    HELP_ACCEPTED,
    HELP_COMPLETED,
    HELP_OFFERED,
    HELP_REQUESTED,
    EventBus,
    build_help_event_payload,
)
from singular.governance.policy import AUTH_AUTO, AUTH_FORCED, MutationGovernancePolicy
from singular.io_utils import append_jsonl_line, atomic_write_text
from singular.life import sandbox

MESSAGE_SCHEMA_V1: dict[str, Any] = {
    "required": {"intent", "task", "evidence", "confidence"},
    "types": {
        "intent": str,
        "task": str,
        "evidence": list,
        "confidence": (float, int),
        "priority": int,
        "agent_id": (str, type(None)),
        "created_at": (float, int),
        "payload": dict,
    },
}


@dataclass(slots=True)
class AgentMessage:
    """Versioned multi-agent message format.

    Version 1 keeps the required fields explicit:
    ``intent``, ``task``, ``evidence`` and ``confidence``.
    """

    intent: Literal[
        "request",
        "offer",
        "warning",
        "knowledge_share",
        "resource_negotiation",
        "sub_problem",
        "answer",
        "help.requested",
        "help.offered",
        "help.accepted",
        "help.completed",
    ]
    task: str
    evidence: list[str]
    confidence: float
    priority: int = 0
    agent_id: str | None = None
    version: int = 1
    created_at: float = field(default_factory=time.time)
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.version not in {1, 2}:
            raise ValueError(f"unsupported message version: {self.version}")
        _validate_payload_schema(self.to_dict(), self.version, schema=MESSAGE_SCHEMA_V1)
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
            "payload": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AgentMessage":
        version = int(payload.get("version", 1))
        validate_message_schema(payload, version=version)
        return cls(
            version=version,
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
            payload=dict(payload.get("payload", {})),
        )


def _validate_payload_schema(
    payload: dict[str, Any],
    version: int,
    *,
    schema: dict[str, Any],
) -> None:
    if version not in {1, 2}:
        raise ValueError(f"unsupported message version: {version}")
    missing = [name for name in schema["required"] if name not in payload]
    if missing:
        raise ValueError(f"missing required field(s): {', '.join(sorted(missing))}")
    for field_name, expected_type in schema["types"].items():
        if field_name not in payload:
            continue
        if not isinstance(payload[field_name], expected_type):
            raise ValueError(f"invalid type for '{field_name}'")


def validate_message_schema(payload: dict[str, Any], *, version: int | None = None) -> None:
    """Validate payload shape and compatible protocol versions.

    Version 2 extends v1 with a generic ``payload`` map and keeps backward
    compatibility with v1 by preserving the required top-level fields.
    """

    effective_version = int(payload.get("version", 1) if version is None else version)
    _validate_payload_schema(payload, effective_version, schema=MESSAGE_SCHEMA_V1)


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
        append_jsonl_line(self.path, message.to_dict())

    def receive(self) -> list[AgentMessage]:
        if not self.path.exists():
            return []
        payload = self.path.read_text(encoding="utf-8")
        atomic_write_text(self.path, "")
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
        append_jsonl_line(self._path, record)

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


@dataclass(slots=True)
class HelpTransferResult:
    status: str
    decision: str
    requester_before: float
    requester_after: float
    helper_before: float
    helper_after: float
    requester_gain: float
    helper_gain: float


@dataclass(slots=True)
class HelpExchangeCoordinator:
    """Coordinate cross-life help events and controlled skill sharing."""

    transport: MessageTransport
    policy: MutationGovernancePolicy
    bus: EventBus | None = None
    memory: CollectiveMemory | None = None
    success_window: int = 20
    _outcomes: dict[tuple[str, str], deque[int]] = field(default_factory=dict)

    def register_outcome(self, *, life_id: str, task: str, success: bool) -> None:
        key = (life_id, task)
        bucket = self._outcomes.setdefault(key, deque(maxlen=max(1, self.success_window)))
        bucket.append(1 if success else 0)

    def success_rate(self, *, life_id: str, task: str) -> float:
        bucket = self._outcomes.get((life_id, task))
        if not bucket:
            return 0.0
        return sum(bucket) / len(bucket)

    def emit_help_requested(self, *, requester_life: str, task: str, attempts: int) -> None:
        payload = build_help_event_payload(
            requester_life=requester_life,
            helper_life=None,
            task=task,
            attempts=attempts,
            metadata={"source": "orchestrator"},
        )
        self.transport.send(
            AgentMessage(
                intent=HELP_REQUESTED,
                task=task,
                evidence=[f"requester:{requester_life}", f"attempts:{attempts}"],
                confidence=1.0,
                agent_id=requester_life,
                payload=payload,
                version=2,
            )
        )
        if self.bus is not None:
            self.bus.publish(HELP_REQUESTED, payload, payload_version=1)

    def transfer_skill(
        self,
        *,
        requester_life: str,
        helper_life: str,
        task: str,
        helper_skill_path: Path,
        requester_skills_dir: Path,
        merge: bool = True,
    ) -> HelpTransferResult:
        requester_before = self.success_rate(life_id=requester_life, task=task)
        helper_before = self.success_rate(life_id=helper_life, task=task)
        skill_name = helper_skill_path.stem
        receiver_target = requester_skills_dir / helper_skill_path.name

        offered = build_help_event_payload(
            requester_life=requester_life,
            helper_life=helper_life,
            task=task,
            attempts=0,
            metadata={"skill": skill_name},
        )
        social_gate = self.policy.record_interlife_interaction(
            source_life=helper_life,
            target_life=requester_life,
            interaction="help.transfer",
            influence_delta=0.05,
        )
        if not social_gate.allowed:
            return HelpTransferResult(
                status="blocked" if social_gate.level == "blocked" else "review_required",
                decision=social_gate.level,
                requester_before=requester_before,
                requester_after=requester_before,
                helper_before=helper_before,
                helper_after=helper_before,
                requester_gain=0.0,
                helper_gain=0.0,
            )
        if self.bus is not None:
            self.bus.publish(HELP_OFFERED, offered, payload_version=1)
        self.transport.send(
            AgentMessage(
                intent=HELP_OFFERED,
                task=task,
                evidence=[f"helper:{helper_life}", f"skill:{skill_name}"],
                confidence=1.0,
                agent_id=helper_life,
                payload=offered,
                version=2,
            )
        )

        helper_code = helper_skill_path.read_text(encoding="utf-8")
        merged_code = helper_code
        if merge and receiver_target.exists():
            local_code = receiver_target.read_text(encoding="utf-8")
            if local_code.strip() != helper_code.strip():
                merged_code = (
                    f"{local_code.rstrip()}\n\n"
                    f"# --- merged_help_from:{helper_life}:{skill_name} ---\n"
                    f"{helper_code.lstrip()}"
                )

        # Sandbox validation before governance-authorized write.
        sandbox.run(f"{merged_code}\nresult = True")
        decision = self.policy.enforce_write(
            receiver_target,
            merged_code,
            root=requester_skills_dir.parent,
            operation="skill_creation",
        )
        if not decision.allowed:
            return HelpTransferResult(
                status="blocked",
                decision=decision.level,
                requester_before=requester_before,
                requester_after=requester_before,
                helper_before=helper_before,
                helper_after=helper_before,
                requester_gain=0.0,
                helper_gain=0.0,
            )
        if decision.level not in {AUTH_AUTO, AUTH_FORCED}:
            return HelpTransferResult(
                status="review_required",
                decision=decision.level,
                requester_before=requester_before,
                requester_after=requester_before,
                helper_before=helper_before,
                helper_after=helper_before,
                requester_gain=0.0,
                helper_gain=0.0,
            )

        accepted_payload = build_help_event_payload(
            requester_life=requester_life,
            helper_life=helper_life,
            task=task,
            attempts=0,
            metadata={"skill": skill_name, "decision": decision.level},
        )
        if self.bus is not None:
            self.bus.publish(HELP_ACCEPTED, accepted_payload, payload_version=1)
        self.transport.send(
            AgentMessage(
                intent=HELP_ACCEPTED,
                task=task,
                evidence=[f"requester:{requester_life}", f"skill:{skill_name}"],
                confidence=1.0,
                agent_id=requester_life,
                payload=accepted_payload,
                version=2,
            )
        )

        self.register_outcome(life_id=requester_life, task=task, success=True)
        self.register_outcome(life_id=helper_life, task=task, success=True)
        requester_after = self.success_rate(life_id=requester_life, task=task)
        helper_after = self.success_rate(life_id=helper_life, task=task)
        requester_gain = requester_after - requester_before
        helper_gain = helper_after - helper_before
        completed_payload = build_help_event_payload(
            requester_life=requester_life,
            helper_life=helper_life,
            task=task,
            attempts=0,
            metadata={
                "skill": skill_name,
                "decision": decision.level,
                "requester_gain": requester_gain,
                "helper_gain": helper_gain,
            },
        )
        if self.bus is not None:
            self.bus.publish(HELP_COMPLETED, completed_payload, payload_version=1)
        self.transport.send(
            AgentMessage(
                intent=HELP_COMPLETED,
                task=task,
                evidence=[f"requester_gain:{requester_gain:.3f}", f"helper_gain:{helper_gain:.3f}"],
                confidence=1.0,
                agent_id=helper_life,
                payload=completed_payload,
                version=2,
            )
        )
        if self.memory is not None:
            self.memory.append(
                {
                    "kind": "help_transfer",
                    "task": task,
                    "requester_life": requester_life,
                    "helper_life": helper_life,
                    "skill": skill_name,
                    "decision": decision.level,
                    "requester_gain": requester_gain,
                    "helper_gain": helper_gain,
                }
            )
        return HelpTransferResult(
            status="completed",
            decision=decision.level,
            requester_before=requester_before,
            requester_after=requester_after,
            helper_before=helper_before,
            helper_after=helper_after,
            requester_gain=requester_gain,
            helper_gain=helper_gain,
        )
