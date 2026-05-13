from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal

from singular.events import HELP_COMPLETED, HELP_OFFERED, HELP_REQUESTED, EventBus
from singular.governance.policy import AUTH_BLOCKED, AUTH_REVIEW_REQUIRED, MutationGovernancePolicy
from singular.multiagent.protocol import (
    AgentMessage,
    CollectiveMemory,
    HelpRequest,
    MessageTransport,
    TaskOffer,
    resolve_conflicts,
)


@dataclass(slots=True)
class LifeTickContext:
    """Multi-agent view of a life-loop tick.

    The loop builds this context after selecting a skill and before choosing the
    concrete mutation operator. This is the earliest point where the runtime
    knows which life, task, and skill are involved, while still being early
    enough to let messages block or bias mutation/action/reproduction choices.
    """

    life_id: str
    task: str
    skill_path: Path
    skills_dir: Path
    score: float
    confidence: float
    governance_allowed: bool
    rivalry: float = 0.0
    peers: tuple[str, ...] = ()
    iteration: int = 0


@dataclass(slots=True)
class MultiAgentDecision:
    """Decision returned to the life loop after inbox/outbox arbitration."""

    mutation_allowed: bool = True
    action_allowed: bool = True
    reproduction_allowed: bool = True
    accepted_offer: TaskOffer | None = None
    conflict_winner: AgentMessage | None = None
    reasons: list[str] = field(default_factory=list)
    inbound: list[AgentMessage] = field(default_factory=list)
    emitted: list[AgentMessage] = field(default_factory=list)


@dataclass(slots=True)
class MultiAgentPolicy:
    """Thresholds for autonomous collaboration during a life tick."""

    low_score_threshold: float = 0.0
    high_confidence_threshold: float = 0.8
    high_rivalry_threshold: float = 0.75
    help_priority: int = 5
    offer_priority: int = 4


class MultiAgentRuntime:
    """Coordinate inbox, outbox, conflict resolution, and help requests.

    The runtime deliberately keeps filesystem writes and mutation materialization
    in the life loop. It only exchanges protocol messages and returns gating
    decisions that the loop applies to mutation acceptance, action execution,
    and reproduction authorization.
    """

    def __init__(
        self,
        *,
        transport: MessageTransport,
        policy: MultiAgentPolicy | None = None,
        governance_policy: MutationGovernancePolicy | None = None,
        bus: EventBus | None = None,
        memory: CollectiveMemory | None = None,
    ) -> None:
        self.transport = transport
        self.policy = policy or MultiAgentPolicy()
        self.governance_policy = governance_policy
        self.bus = bus
        self.memory = memory
        self.inbox: list[AgentMessage] = []
        self.outbox: list[AgentMessage] = []

    def drain_inbox(self) -> list[AgentMessage]:
        messages = self.transport.receive()
        self.inbox.extend(messages)
        return messages

    def emit(self, message: AgentMessage) -> AgentMessage:
        self.transport.send(message)
        self.outbox.append(message)
        if self.memory is not None:
            self.memory.append({"kind": "multiagent_message", "message": message.to_dict()})
        if self.bus is not None and message.intent.startswith("help."):
            self.bus.publish(message.intent, message.payload, payload_version=message.version)
        return message

    def begin_tick(self, context: LifeTickContext) -> MultiAgentDecision:
        """Consult inbound messages and emit help/offer/refusal messages.

        Policy:
        * low score => request help;
        * high confidence => offer the selected skill;
        * blocked governance or high rivalry => refuse collaboration and gate
          mutation/action/reproduction for this tick.
        """

        inbound = [msg for msg in self.drain_inbox() if self._matches_context(msg, context)]
        winners = resolve_conflicts(inbound)
        conflict_winner = winners.get(context.task)
        emitted: list[AgentMessage] = []
        reasons: list[str] = []

        governance_allowed = context.governance_allowed and self._governance_allows(context)
        rivalry_high = context.rivalry >= self.policy.high_rivalry_threshold
        if not governance_allowed or rivalry_high:
            reasons.append("governance_blocked" if not governance_allowed else "rivalry_high")
            emitted.extend(self._refuse_inbound(context, inbound, reasons[-1]))
            return MultiAgentDecision(
                mutation_allowed=False,
                action_allowed=False,
                reproduction_allowed=False,
                conflict_winner=conflict_winner,
                reasons=reasons,
                inbound=inbound,
                emitted=emitted,
            )

        accepted_offer: TaskOffer | None = None
        if conflict_winner and conflict_winner.intent == HELP_OFFERED:
            accepted_offer = TaskOffer.from_message(conflict_winner)
            reasons.append("accepted_best_offer")

        if context.score <= self.policy.low_score_threshold:
            emitted.append(self.emit(HelpRequest.from_context(context).to_message()))
            reasons.append("requested_help_low_score")

        if context.confidence >= self.policy.high_confidence_threshold:
            for peer in context.peers or (None,):
                emitted.append(self.emit(TaskOffer.from_context(context, receiver_id=peer).to_message()))
            reasons.append("offered_skill_high_confidence")

        return MultiAgentDecision(
            accepted_offer=accepted_offer,
            conflict_winner=conflict_winner,
            reasons=reasons,
            inbound=inbound,
            emitted=emitted,
        )

    def complete_tick(
        self,
        context: LifeTickContext,
        *,
        accepted: bool,
        score_before: float,
        score_after: float,
    ) -> AgentMessage:
        intent: Literal["help.completed", "answer"] = HELP_COMPLETED if accepted else "answer"
        message = AgentMessage(
            intent=intent,
            task=context.task,
            evidence=[
                f"skill:{context.skill_path.name}",
                f"accepted:{accepted}",
                f"score_before:{score_before:.6f}",
                f"score_after:{score_after:.6f}",
            ],
            confidence=max(0.0, min(1.0, context.confidence)),
            priority=1,
            agent_id=context.life_id,
            payload={
                "iteration": context.iteration,
                "skill_path": str(context.skill_path),
                "accepted": accepted,
                "score_before": score_before,
                "score_after": score_after,
            },
            version=2,
        )
        return self.emit(message)

    def gate_reproduction(
        self,
        *,
        parents: Iterable[str],
        governance_allowed: bool,
        rivalry: float,
        task: str,
    ) -> MultiAgentDecision:
        context = LifeTickContext(
            life_id="ecosystem",
            task=task,
            skill_path=Path(task),
            skills_dir=Path("."),
            score=0.0,
            confidence=0.0,
            governance_allowed=governance_allowed,
            rivalry=rivalry,
            peers=tuple(parents),
        )
        if governance_allowed and rivalry < self.policy.high_rivalry_threshold:
            return MultiAgentDecision(reasons=["reproduction_allowed"])
        reason = "governance_blocked" if not governance_allowed else "rivalry_high"
        message = AgentMessage(
            intent="warning",
            task=task,
            evidence=[reason, *(f"parent:{parent}" for parent in parents)],
            confidence=1.0,
            priority=self.policy.help_priority,
            agent_id="multiagent-runtime",
            payload={"reason": reason, "rivalry": rivalry},
            version=2,
        )
        return MultiAgentDecision(
            mutation_allowed=False,
            action_allowed=False,
            reproduction_allowed=False,
            reasons=[reason],
            emitted=[self.emit(message)],
        )

    def _matches_context(self, message: AgentMessage, context: LifeTickContext) -> bool:
        target = message.payload.get("receiver_id") or message.payload.get("requester_life") or None
        return message.task == context.task and (target in {None, context.life_id})

    def _governance_allows(self, context: LifeTickContext) -> bool:
        if self.governance_policy is None:
            return True
        if not self.governance_policy.mutations_enabled():
            return False
        decision = self.governance_policy.simulate_write(
            context.skill_path,
            root=context.skills_dir.parent,
        )
        return decision.allowed and decision.level not in {AUTH_BLOCKED, AUTH_REVIEW_REQUIRED}

    def _refuse_inbound(
        self,
        context: LifeTickContext,
        inbound: list[AgentMessage],
        reason: str,
    ) -> list[AgentMessage]:
        emitted: list[AgentMessage] = []
        targets = [msg.agent_id for msg in inbound if msg.agent_id and msg.agent_id != context.life_id]
        if not targets:
            targets = [None]
        for target in targets:
            emitted.append(
                self.emit(
                    AgentMessage(
                        intent="help.refused",
                        task=context.task,
                        evidence=[reason, f"skill:{context.skill_path.name}"],
                        confidence=1.0,
                        priority=self.policy.help_priority,
                        agent_id=context.life_id,
                        payload={"receiver_id": target, "reason": reason},
                        version=2,
                    )
                )
            )
        return emitted
