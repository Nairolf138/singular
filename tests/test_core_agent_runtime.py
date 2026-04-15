from __future__ import annotations

import pytest

from singular.core.agent_runtime import (
    ActionRequest,
    ActionResult,
    AgentRuntime,
    Intent,
    PerceptEvent,
    RuntimeEvent,
    RuntimeEventBus,
)


class _PerceptionStub:
    def collect(self) -> list[PerceptEvent]:
        return [
            PerceptEvent(
                event_type="vision",
                source="camera",
                payload={"object": "door"},
            )
        ]


class _MindStub:
    def propose_intent(self, percept: PerceptEvent) -> Intent | None:
        return Intent(goal=f"inspect:{percept.event_type}", confidence=0.9)

    def propose_action(self, intent: Intent, percept: PerceptEvent) -> ActionRequest | None:
        return ActionRequest(
            action_type="os.notify",
            parameters={"goal": intent.goal, "source": percept.source},
            intent_goal=intent.goal,
        )


class _ActionStub:
    def execute(self, request: ActionRequest) -> ActionResult:
        return ActionResult(
            action_type=request.action_type,
            success=True,
            message="done",
            audit={"intent_goal": request.intent_goal},
        )


def test_agent_runtime_step_orchestrates_ports_and_events() -> None:
    bus = RuntimeEventBus()
    seen_topics: list[str] = []
    seen_events: list[RuntimeEvent] = []

    for topic in (
        "perception.received",
        "mind.intent.proposed",
        "action.requested",
        "action.completed",
    ):
        bus.subscribe(topic, lambda event, *, _topic=topic: seen_topics.append(_topic))
        bus.subscribe(topic, lambda event: seen_events.append(event))

    runtime = AgentRuntime(
        perception=_PerceptionStub(),
        mind=_MindStub(),
        action=_ActionStub(),
        event_bus=bus,
    )

    results = runtime.step()

    assert len(results) == 1
    assert results[0].success is True
    assert seen_topics == [
        "perception.received",
        "mind.intent.proposed",
        "action.requested",
        "action.completed",
    ]
    assert all(event.schema_version == runtime.schema_version for event in seen_events)


def test_agent_runtime_rejects_schema_version_mismatch() -> None:
    class _BadPerception:
        def collect(self) -> list[PerceptEvent]:
            return [
                PerceptEvent(
                    event_type="os.event",
                    source="kernel",
                    payload={"event": "wake"},
                    schema_version="2.0",
                )
            ]

    runtime = AgentRuntime(
        perception=_BadPerception(),
        mind=_MindStub(),
        action=_ActionStub(),
    )

    with pytest.raises(ValueError, match="Schema version mismatch"):
        runtime.step()
