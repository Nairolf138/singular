"""Central runtime orchestration for perception, mind and action ports."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Protocol
from uuid import uuid4

DEFAULT_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class PerceptEvent:
    """Structured perception signal captured by the runtime."""

    event_type: str
    payload: dict[str, Any]
    source: str
    schema_version: str = DEFAULT_SCHEMA_VERSION
    observed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True)
class Intent:
    """Objective proposed by the mind layer."""

    goal: str
    rationale: str = ""
    mood: str = "neutral"
    memory_refs: tuple[str, ...] = ()
    confidence: float = 0.0
    schema_version: str = DEFAULT_SCHEMA_VERSION


@dataclass(frozen=True)
class ActionRequest:
    """Action demanded by the runtime and sent to the action port."""

    action_type: str
    parameters: dict[str, Any] = field(default_factory=dict)
    intent_goal: str = ""
    schema_version: str = DEFAULT_SCHEMA_VERSION
    requested_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True)
class ActionResult:
    """Execution result and audit metadata for an action."""

    action_type: str
    success: bool
    message: str = ""
    error: str | None = None
    audit: dict[str, Any] = field(default_factory=dict)
    schema_version: str = DEFAULT_SCHEMA_VERSION
    completed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True)
class RuntimeEvent:
    """Envelope emitted on the internal runtime event bus."""

    topic: str
    payload: Any
    schema_version: str = DEFAULT_SCHEMA_VERSION
    event_id: str = field(default_factory=lambda: uuid4().hex)
    emitted_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


EventHandler = Callable[[RuntimeEvent], None]


class RuntimeEventBus:
    """In-memory pub/sub bus with topic-based subscriptions."""

    def __init__(self, *, schema_version: str = DEFAULT_SCHEMA_VERSION) -> None:
        self.schema_version = schema_version
        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, topic: str, handler: EventHandler) -> None:
        handlers = self._subscribers[topic]
        if handler not in handlers:
            handlers.append(handler)

    def publish(self, topic: str, payload: Any) -> RuntimeEvent:
        event = RuntimeEvent(
            topic=topic,
            payload=payload,
            schema_version=self.schema_version,
        )
        for handler in list(self._subscribers.get(topic, [])):
            handler(event)
        return event


class PerceptionPort(Protocol):
    """Port producing structured perception events."""

    def collect(self) -> list[PerceptEvent]:
        """Return new percepts for the current runtime step."""


class MindPort(Protocol):
    """Port transforming perception into intent and action requests."""

    def propose_intent(self, percept: PerceptEvent) -> Intent | None:
        """Propose a goal based on one percept."""

    def propose_action(self, intent: Intent, percept: PerceptEvent) -> ActionRequest | None:
        """Translate one intent into an executable action request."""


class ActionPort(Protocol):
    """Port executing authorized actions."""

    def execute(self, request: ActionRequest) -> ActionResult:
        """Execute one action request and return audited output."""


class AgentRuntime:
    """Central runtime orchestrating perception, mind and action ports."""

    def __init__(
        self,
        *,
        perception: PerceptionPort,
        mind: MindPort,
        action: ActionPort,
        event_bus: RuntimeEventBus | None = None,
        schema_version: str = DEFAULT_SCHEMA_VERSION,
    ) -> None:
        self.perception = perception
        self.mind = mind
        self.action = action
        self.schema_version = schema_version
        self.event_bus = event_bus or RuntimeEventBus(schema_version=schema_version)

    def step(self) -> list[ActionResult]:
        """Run one full runtime step.

        Flow:
        1. collect perception events,
        2. let the mind propose intent/action,
        3. execute allowed actions,
        4. publish all lifecycle events on the internal bus.
        """

        percepts = self.perception.collect()
        results: list[ActionResult] = []
        for percept in percepts:
            self._ensure_schema_version(percept.schema_version)
            self.event_bus.publish("perception.received", percept)

            intent = self.mind.propose_intent(percept)
            if intent is None:
                self.event_bus.publish("mind.intent.skipped", {"percept": percept})
                continue
            self._ensure_schema_version(intent.schema_version)
            self.event_bus.publish("mind.intent.proposed", intent)

            request = self.mind.propose_action(intent, percept)
            if request is None:
                self.event_bus.publish("action.request.skipped", {"intent": intent})
                continue
            self._ensure_schema_version(request.schema_version)
            self.event_bus.publish("action.requested", request)

            result = self.action.execute(request)
            self._ensure_schema_version(result.schema_version)
            self.event_bus.publish("action.completed", result)
            results.append(result)

        return results

    def _ensure_schema_version(self, candidate: str) -> None:
        if candidate != self.schema_version:
            raise ValueError(
                "Schema version mismatch: "
                f"runtime={self.schema_version} candidate={candidate}"
            )
