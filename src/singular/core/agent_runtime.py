"""Central runtime orchestration for perception, mind and action ports."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from singular.security.policy_engine import ActionPolicyEngine
from uuid import uuid4
from singular.memory import add_causal_trace, add_episode, get_mem_dir
from singular.cognition.self_observation import SelfObservationService
from singular.embodiment import Acknowledgement, Command, EmergencyStop, Observation
from singular.morals import MoralAction, MoralDecisionEngine
from singular.morals import MoralContextBuilder
from singular.identity.core import IdentityCoreService

DEFAULT_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class Intent:
    """Objective proposed by the mind layer."""

    goal: str
    rationale: str = ""
    mood: str = "neutral"
    memory_refs: tuple[str, ...] = ()
    confidence: float = 0.0
    schema_version: str = DEFAULT_SCHEMA_VERSION


# Backwards-compatible names now point at the shared embodiment contracts.
PerceptEvent = Observation
ActionRequest = Command
ActionResult = Acknowledgement


@dataclass(frozen=True)
class RuntimeEvent:
    """Envelope emitted on the internal runtime event bus."""

    topic: str
    payload: Any
    schema_version: str = DEFAULT_SCHEMA_VERSION
    event_id: str = field(default_factory=lambda: uuid4().hex)
    emitted_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True)
class CausalTrace:
    """Correlation record linking input, decision, action and measured result."""

    trace_id: str
    input: dict[str, Any]
    decision: dict[str, Any]
    action: dict[str, Any]
    result: dict[str, Any]
    schema_version: str = DEFAULT_SCHEMA_VERSION
    recorded_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True)
class RuntimeSafetyConfig:
    """Safety controls applied to runtime action execution."""

    global_stop_hotkey: str = "ctrl+shift+."
    max_actions_per_minute: int = 60
    watchdog_window_size: int = 12
    watchdog_repeat_action_threshold: int = 10
    max_critical_errors: int = 3


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

    def propose_action(
        self, intent: Intent, percept: PerceptEvent
    ) -> ActionRequest | None:
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
        policy_engine: ActionPolicyEngine | None = None,
        schema_version: str = DEFAULT_SCHEMA_VERSION,
        safety: RuntimeSafetyConfig | None = None,
        stop_signal: Callable[[], bool] | None = None,
        moral_engine: MoralDecisionEngine | None = None,
        resource_gate: Callable[[ActionRequest], bool | tuple[bool, str]] | None = None,
        emergency_stop: EmergencyStop | None = None,
        self_observation: SelfObservationService | None = None,
    ) -> None:
        self.perception = perception
        self.mind = mind
        self.action = action
        self.schema_version = schema_version
        self.event_bus = event_bus or RuntimeEventBus(schema_version=schema_version)
        self.policy_engine = policy_engine or ActionPolicyEngine()
        self.moral_engine = moral_engine or MoralDecisionEngine(journal=add_episode)
        self.moral_context_builder = MoralContextBuilder(
            IdentityCoreService(get_mem_dir()), journal=add_episode
        )
        self.resource_gate = resource_gate
        self.emergency_stop = emergency_stop or EmergencyStop()
        self.safety = safety or RuntimeSafetyConfig()
        self._stop_signal = stop_signal
        self._global_stop_requested = False
        self._disabled = False
        self._critical_error_count = 0
        self._action_timestamps: deque[float] = deque()
        self._recent_actions: deque[str] = deque(
            maxlen=max(self.safety.watchdog_window_size, 1)
        )
        self._causal_traces: deque[CausalTrace] = deque(maxlen=200)
        self.self_observation = self_observation or SelfObservationService(
            get_mem_dir() / "self_model.json"
        )

    @property
    def disabled(self) -> bool:
        """Whether the runtime has been automatically disabled."""

        return self._disabled

    def request_global_stop(self) -> None:
        """Request an immediate global stop (hotkey equivalent)."""

        self._global_stop_requested = True
        self.emergency_stop.engage("runtime_global_stop")
        stop = getattr(self.action, "emergency_stop", None)
        if callable(stop):
            stop("runtime_global_stop")

    def step(self) -> list[ActionResult]:
        """Run one full runtime step.

        Flow:
        1. collect perception events,
        2. let the mind propose intent/action,
        3. execute allowed actions,
        4. publish all lifecycle events on the internal bus.
        """

        if self._disabled:
            self.event_bus.publish(
                "runtime.disabled",
                {
                    "reason": "critical_error_threshold_reached",
                    "critical_error_count": self._critical_error_count,
                    "max_critical_errors": self.safety.max_critical_errors,
                },
            )
            return []

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

            action = MoralAction(request.action_type, request.parameters, intent.rationale)
            moral_context = self.moral_context_builder.build(
                action, request.parameters.get("moral_context", {})
            )
            moral_decision = self.moral_engine.evaluate(
                action,
                moral_context.consequences,
                moral_context.affected_parties,
                moral_context.identity_commitments,
                moral_context.uncertainty,
            )
            self.event_bus.publish("action.moral.decision", moral_decision)

            if self._stop_requested():
                self.event_bus.publish(
                    "runtime.global_stop",
                    {
                        "reason": "hotkey_triggered",
                        "hotkey": self.safety.global_stop_hotkey,
                    },
                )
                break

            if self._is_rate_limited():
                self._record_critical_error("max_actions_per_minute_exceeded")
                self.event_bus.publish(
                    "runtime.rate_limited",
                    {
                        "reason": "max_actions_per_minute_exceeded",
                        "max_actions_per_minute": self.safety.max_actions_per_minute,
                        "critical_error_count": self._critical_error_count,
                    },
                )
                break

            if self._watchdog_triggered(request.action_type):
                self._record_critical_error("watchdog_abnormal_action_loop")
                self.event_bus.publish(
                    "runtime.watchdog_stopped",
                    {
                        "reason": "watchdog_abnormal_action_loop",
                        "action_type": request.action_type,
                        "watchdog_window_size": self.safety.watchdog_window_size,
                        "repeat_threshold": self.safety.watchdog_repeat_action_threshold,
                        "critical_error_count": self._critical_error_count,
                    },
                )
                break

            decision = self.policy_engine.evaluate(request)
            self.event_bus.publish(
                "action.policy.decision",
                {
                    "request": request,
                    "allowed": decision.allowed,
                    "blocked": decision.blocked,
                    "reason": decision.reason,
                    "rule_id": decision.rule_id,
                    "risk_level": decision.risk_level,
                    "dry_run": decision.dry_run,
                },
            )
            if decision.blocked:
                result = ActionResult(
                    action_type=request.action_type,
                    success=False,
                    message="blocked by policy engine",
                    error=decision.reason,
                    audit={
                        "policy": {
                            "allowed": decision.allowed,
                            "blocked": decision.blocked,
                            "reason": decision.reason,
                            "rule_id": decision.rule_id,
                            "risk_level": decision.risk_level,
                            "dry_run": decision.dry_run,
                        }
                    },
                )
                self.event_bus.publish("action.blocked", result)
                self._record_causal_trace(
                    percept=percept,
                    intent=intent,
                    request=request,
                    result=result,
                    decision=decision,
                )
                results.append(result)
                continue

            if moral_decision.veto:
                result = ActionResult(
                    action_type=request.action_type,
                    success=False,
                    message="blocked by moral veto",
                    error=moral_decision.veto_reason,
                    audit={"moral": moral_decision.to_dict()},
                    command_id=request.command_id,
                    actual={"executed": False},
                )
                self.event_bus.publish("action.moral.vetoed", result)
                self._record_causal_trace(
                    percept=percept,
                    intent=intent,
                    request=request,
                    result=result,
                    decision=decision,
                )
                results.append(result)
                continue

            resource_allowed, resource_reason = self._resources_allow(request)
            self.event_bus.publish(
                "action.resource.decision",
                {
                    "request": request,
                    "allowed": resource_allowed,
                    "reason": resource_reason,
                },
            )
            if not resource_allowed:
                result = ActionResult(
                    action_type=request.action_type,
                    success=False,
                    message="blocked by resource limits",
                    error=resource_reason,
                    audit={"resource": {"allowed": False, "reason": resource_reason}},
                    command_id=request.command_id,
                    actual={"executed": False},
                )
                self.event_bus.publish("action.resource.blocked", result)
                self._record_causal_trace(
                    percept=percept,
                    intent=intent,
                    request=request,
                    result=result,
                    decision=decision,
                )
                results.append(result)
                continue

            if decision.dry_run:
                self._register_action(request.action_type)
                result = ActionResult(
                    action_type=request.action_type,
                    success=True,
                    message="simulated (dry-run)",
                    audit={
                        "policy": {
                            "allowed": decision.allowed,
                            "blocked": decision.blocked,
                            "reason": decision.reason,
                            "rule_id": decision.rule_id,
                            "risk_level": decision.risk_level,
                            "dry_run": decision.dry_run,
                        }
                    },
                )
                self.event_bus.publish("action.simulated", result)
                self._record_causal_trace(
                    percept=percept,
                    intent=intent,
                    request=request,
                    result=result,
                    decision=decision,
                )
                results.append(result)
                continue

            try:
                result = self.action.execute(request)
            except Exception as exc:  # pragma: no cover - defensive contract hardening
                self._record_critical_error("action_execution_exception")
                result = ActionResult(
                    action_type=request.action_type,
                    success=False,
                    message="action execution failed",
                    error=str(exc),
                    audit={
                        "policy": {
                            "allowed": decision.allowed,
                            "blocked": decision.blocked,
                            "reason": decision.reason,
                            "rule_id": decision.rule_id,
                            "risk_level": decision.risk_level,
                            "dry_run": decision.dry_run,
                        },
                        "critical_error": True,
                    },
                )
                self.event_bus.publish("action.failed", result)
                self._record_causal_trace(
                    percept=percept,
                    intent=intent,
                    request=request,
                    result=result,
                    decision=decision,
                )
                results.append(result)
                if self._disabled:
                    break
                continue

            self._ensure_schema_version(result.schema_version)
            self._register_action(request.action_type)
            enriched_audit = dict(result.audit)
            enriched_audit["moral"] = moral_decision.to_dict()
            enriched_audit["policy"] = {
                "allowed": decision.allowed,
                "blocked": decision.blocked,
                "reason": decision.reason,
                "rule_id": decision.rule_id,
                "risk_level": decision.risk_level,
                "dry_run": decision.dry_run,
            }
            result = ActionResult(
                action_type=result.action_type,
                success=result.success,
                message=result.message,
                error=result.error,
                audit=enriched_audit,
                schema_version=result.schema_version,
                completed_at=result.completed_at,
                command_id=result.command_id or request.command_id,
                actual=dict(result.actual),
            )
            if self._is_critical_result(result):
                self._record_critical_error("critical_action_result")
            self.event_bus.publish("action.completed", result)
            self._record_causal_trace(
                percept=percept,
                intent=intent,
                request=request,
                result=result,
                decision=decision,
            )
            results.append(result)
            if self._disabled:
                break

        return results

    def _resources_allow(self, request: ActionRequest) -> tuple[bool, str]:
        if self.resource_gate is None:
            return True, "within_limits"
        verdict = self.resource_gate(request)
        if isinstance(verdict, tuple):
            return bool(verdict[0]), str(verdict[1])
        return bool(verdict), "within_limits" if verdict else "resource_limit_exceeded"

    def _ensure_schema_version(self, candidate: str) -> None:
        if candidate != self.schema_version:
            raise ValueError(
                "Schema version mismatch: "
                f"runtime={self.schema_version} candidate={candidate}"
            )

    def _stop_requested(self) -> bool:
        if self._global_stop_requested:
            return True
        if self._stop_signal is None:
            return False
        try:
            return bool(self._stop_signal())
        except Exception:
            return False

    def _register_action(self, action_type: str) -> None:
        import time

        now = time.monotonic()
        self._action_timestamps.append(now)
        self._trim_action_window(now)
        self._recent_actions.append(action_type)

    def _trim_action_window(self, now: float) -> None:
        one_minute = 60.0
        while self._action_timestamps and now - self._action_timestamps[0] > one_minute:
            self._action_timestamps.popleft()

    def _is_rate_limited(self) -> bool:
        import time

        if self.safety.max_actions_per_minute <= 0:
            return False
        now = time.monotonic()
        self._trim_action_window(now)
        return len(self._action_timestamps) >= self.safety.max_actions_per_minute

    def _watchdog_triggered(self, action_type: str) -> bool:
        threshold = self.safety.watchdog_repeat_action_threshold
        if threshold <= 0 or len(self._recent_actions) < threshold - 1:
            return False
        return list(self._recent_actions)[-(threshold - 1) :] == [action_type] * (
            threshold - 1
        )

    def _is_critical_result(self, result: ActionResult) -> bool:
        if result.success:
            return False
        policy = result.audit.get("policy") if isinstance(result.audit, dict) else None
        if isinstance(policy, dict) and policy.get("risk_level") == "critical":
            return True
        if isinstance(result.error, str) and "critical" in result.error.lower():
            return True
        return (
            bool(result.audit.get("critical_error", False))
            if isinstance(result.audit, dict)
            else False
        )

    def _record_critical_error(self, reason: str) -> None:
        self._critical_error_count += 1
        self.event_bus.publish(
            "runtime.critical_error",
            {
                "reason": reason,
                "critical_error_count": self._critical_error_count,
                "max_critical_errors": self.safety.max_critical_errors,
            },
        )
        if self._critical_error_count >= max(self.safety.max_critical_errors, 1):
            self._disabled = True
            self.event_bus.publish(
                "runtime.auto_disabled",
                {
                    "reason": "critical_error_threshold_reached",
                    "critical_error_count": self._critical_error_count,
                    "max_critical_errors": self.safety.max_critical_errors,
                },
            )

    def _record_causal_trace(
        self,
        *,
        percept: PerceptEvent,
        intent: Intent,
        request: ActionRequest,
        result: ActionResult,
        decision: Any,
    ) -> None:
        policy_details = {
            "allowed": getattr(decision, "allowed", None),
            "blocked": getattr(decision, "blocked", None),
            "reason": getattr(decision, "reason", None),
            "rule_id": getattr(decision, "rule_id", None),
            "risk_level": getattr(decision, "risk_level", None),
            "dry_run": getattr(decision, "dry_run", None),
        }
        gain_loss = 1.0 if result.success else -1.0
        trace = CausalTrace(
            trace_id=uuid4().hex,
            input={
                "kind": "percept_event",
                "event_type": percept.event_type,
                "source": percept.source,
                "payload": percept.payload,
            },
            decision={
                "intent_goal": intent.goal,
                "intent_rationale": intent.rationale,
                "policy": policy_details,
            },
            action={
                "action_type": request.action_type,
                "parameters": request.parameters,
            },
            result={
                "success": result.success,
                "message": result.message,
                "error": result.error,
                "command_id": result.command_id,
                "actual": result.actual,
                "gain_loss": gain_loss,
                "objective_impact": {
                    "objective": intent.goal,
                    "impact": gain_loss,
                },
            },
            schema_version=self.schema_version,
        )
        self._causal_traces.append(trace)
        self.event_bus.publish("causal.trace", trace)
        payload = {
            "ts": trace.recorded_at,
            "trace_id": trace.trace_id,
            "pipeline": "agent_runtime.embodiment",
            "input": trace.input,
            "decision": trace.decision,
            "action": trace.action,
            "result": trace.result,
        }
        add_causal_trace(payload)
        add_episode({"event": "embodiment.action.result", **payload})
        # The persisted trace id is the evidence anchor; never learn from an
        # unreferenced interpretation of an action result.
        self.self_observation.observe_trace(
            payload, evidence_ref=f"causal:{trace.trace_id}"
        )
