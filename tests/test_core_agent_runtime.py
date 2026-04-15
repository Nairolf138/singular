from __future__ import annotations

import pytest

from security.policy_engine import ActionPolicyEngine, PolicyRule
from singular.core.agent_runtime import (
    ActionRequest,
    ActionResult,
    AgentRuntime,
    Intent,
    PerceptEvent,
    RuntimeEvent,
    RuntimeEventBus,
    RuntimeSafetyConfig,
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
            parameters={
                "goal": intent.goal,
                "source": percept.source,
                "application": "terminal",
                "window": "main",
                "screen_zone": "center",
            },
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
    assert results[0].audit["policy"]["allowed"] is True



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



def test_agent_runtime_blocks_action_not_allowlisted() -> None:
    decisions: list[dict[str, object]] = []
    runtime = AgentRuntime(
        perception=_PerceptionStub(),
        mind=_MindStub(),
        action=_ActionStub(),
        policy_engine=ActionPolicyEngine(
            rules=[
                PolicyRule(
                    rule_id="allow_browser_only",
                    applications=frozenset({"browser"}),
                    windows=frozenset({"*"}),
                    screen_zones=frozenset({"*"}),
                    action_types=frozenset({"os.notify"}),
                )
            ],
            decision_logger=decisions.append,
        ),
    )

    results = runtime.step()

    assert len(results) == 1
    assert results[0].success is False
    assert results[0].error == "action_not_allowlisted"
    assert decisions[-1]["blocked"] is True
    assert decisions[-1]["reason"] == "action_not_allowlisted"



def test_agent_runtime_simulates_dry_run_without_executing_action_port() -> None:
    class _ActionSpy(_ActionStub):
        def __init__(self) -> None:
            self.called = False

        def execute(self, request: ActionRequest) -> ActionResult:
            self.called = True
            return super().execute(request)

    action_spy = _ActionSpy()
    runtime = AgentRuntime(
        perception=_PerceptionStub(),
        mind=_MindStub(),
        action=action_spy,
        policy_engine=ActionPolicyEngine(dry_run=True),
    )

    results = runtime.step()

    assert len(results) == 1
    assert results[0].success is True
    assert results[0].message == "simulated (dry-run)"
    assert action_spy.called is False



def test_agent_runtime_requires_human_confirmation_for_critical_actions() -> None:
    class _CriticalMind(_MindStub):
        def propose_action(self, intent: Intent, percept: PerceptEvent) -> ActionRequest | None:
            return ActionRequest(
                action_type="os.notify",
                parameters={
                    "application": "terminal",
                    "window": "main",
                    "screen_zone": "center",
                    "risk_score": 0.95,
                    "critical": True,
                },
                intent_goal=intent.goal,
            )

    runtime = AgentRuntime(
        perception=_PerceptionStub(),
        mind=_CriticalMind(),
        action=_ActionStub(),
        policy_engine=ActionPolicyEngine(
            rules=[
                PolicyRule(
                    rule_id="allow_terminal_notify",
                    applications=frozenset({"terminal"}),
                    windows=frozenset({"main"}),
                    screen_zones=frozenset({"center"}),
                    action_types=frozenset({"os.notify"}),
                )
            ]
        ),
    )

    results = runtime.step()

    assert len(results) == 1
    assert results[0].success is False
    assert results[0].error == "critical_action_requires_human_confirmation"


def test_agent_runtime_global_stop_hotkey_interrupts_step() -> None:
    bus = RuntimeEventBus()
    seen: list[str] = []
    bus.subscribe("runtime.global_stop", lambda event: seen.append(event.topic))
    runtime = AgentRuntime(
        perception=_PerceptionStub(),
        mind=_MindStub(),
        action=_ActionStub(),
        event_bus=bus,
    )
    runtime.request_global_stop()

    results = runtime.step()

    assert results == []
    assert seen == ["runtime.global_stop"]



def test_agent_runtime_watchdog_stops_abnormal_action_loop() -> None:
    class _ManyPercepts:
        def collect(self) -> list[PerceptEvent]:
            return [
                PerceptEvent(event_type=f"vision-{idx}", source="camera", payload={"idx": idx})
                for idx in range(8)
            ]

    runtime = AgentRuntime(
        perception=_ManyPercepts(),
        mind=_MindStub(),
        action=_ActionStub(),
        safety=RuntimeSafetyConfig(
            watchdog_window_size=6,
            watchdog_repeat_action_threshold=4,
            max_critical_errors=5,
        ),
    )

    results = runtime.step()

    assert len(results) == 3



def test_agent_runtime_enforces_max_actions_per_minute() -> None:
    class _ManyPercepts:
        def collect(self) -> list[PerceptEvent]:
            return [
                PerceptEvent(event_type=f"vision-{idx}", source="camera", payload={"idx": idx})
                for idx in range(10)
            ]

    runtime = AgentRuntime(
        perception=_ManyPercepts(),
        mind=_MindStub(),
        action=_ActionStub(),
        safety=RuntimeSafetyConfig(max_actions_per_minute=2, max_critical_errors=5),
    )

    results = runtime.step()

    assert len(results) == 2



def test_agent_runtime_auto_disables_after_critical_errors() -> None:
    class _AlwaysFailAction:
        def execute(self, request: ActionRequest) -> ActionResult:
            return ActionResult(
                action_type=request.action_type,
                success=False,
                error="critical: unrecoverable",
            )

    class _TwoPercepts:
        def collect(self) -> list[PerceptEvent]:
            return [
                PerceptEvent(event_type="vision-a", source="camera", payload={}),
                PerceptEvent(event_type="vision-b", source="camera", payload={}),
            ]

    runtime = AgentRuntime(
        perception=_TwoPercepts(),
        mind=_MindStub(),
        action=_AlwaysFailAction(),
        safety=RuntimeSafetyConfig(max_critical_errors=2),
    )

    first_results = runtime.step()
    second_results = runtime.step()

    assert len(first_results) == 2
    assert runtime.disabled is True
    assert second_results == []
