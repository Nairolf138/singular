from __future__ import annotations

from singular.cognition.reflect import ActionHypothesis, reflect_action
from singular.events import Event, EventBus


def test_reflect_action_returns_structured_decision_and_event_payload() -> None:
    events: list[Event] = []
    bus = EventBus(mode="sync")
    bus.subscribe("decision.made", events.append)

    decision = reflect_action(
        [
            ActionHypothesis(
                action="wait",
                long_term=0.2,
                sandbox_risk=0.0,
                resource_cost=0.1,
            ),
            ActionHypothesis(
                action="mutate",
                long_term=0.9,
                sandbox_risk=0.2,
                resource_cost=0.2,
                metadata={
                    "hypotheses": ["mutation may improve the objective"],
                    "risks": ["mutation could regress tests"],
                    "benefits": ["higher expected score"],
                },
            ),
        ],
        bus=bus,
        event_context={"run_id": "r1"},
    )

    assert decision.action == "mutate"
    assert decision.action_recommended == "execute"
    assert decision.confidence > 0.5
    assert decision.hypotheses == ["mutation may improve the objective"]
    assert "mutation could regress tests" in decision.risks
    assert decision.benefits == ["higher expected score"]
    assert decision.assessments[0].action == "mutate"
    assert events[0].payload["decision"]["confidence"] == decision.confidence
    assert events[0].payload["decision"]["action_recommended"] == "execute"
    assert events[0].payload["context"] == {"run_id": "r1"}


def test_reflect_action_documents_empty_hypotheses() -> None:
    decision = reflect_action([], bus=EventBus(mode="sync"))

    assert decision.action is None
    assert decision.confidence == 0.0
    assert decision.action_recommended == "collect_more_hypotheses"
    assert decision.risks == ["no candidate action was available to assess"]


def test_thinking_helpers_are_packaged_under_singular_namespace() -> None:
    from singular.thinking import EpisodicMemory, evaluate_actions

    memory = EpisodicMemory()
    memory.remember("act", "result")

    assert memory.recall("act") == "result"
    assert callable(evaluate_actions)
