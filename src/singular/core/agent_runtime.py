"""Central runtime orchestration for perception, mind and action ports."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from security.policy_engine import ActionPolicyEngine
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
        policy_engine: ActionPolicyEngine | None = None,
        schema_version: str = DEFAULT_SCHEMA_VERSION,
        safety: RuntimeSafetyConfig | None = None,
        stop_signal: Callable[[], bool] | None = None,
    ) -> None:
        self.perception = perception
        self.mind = mind
        self.action = action
        self.schema_version = schema_version
        self.event_bus = event_bus or RuntimeEventBus(schema_version=schema_version)
        self.policy_engine = policy_engine or ActionPolicyEngine()
        self.safety = safety or RuntimeSafetyConfig()
        self._stop_signal = stop_signal
        self._global_stop_requested = False
        self._disabled = False
        self._critical_error_count = 0
        self._action_timestamps: deque[float] = deque()
        self._recent_actions: deque[str] = deque(maxlen=max(self.safety.watchdog_window_size, 1))

    @property
    def disabled(self) -> bool:
        """Whether the runtime has been automatically disabled."""

        return self._disabled

    def request_global_stop(self) -> None:
        """Request an immediate global stop (hotkey equivalent)."""

        self._global_stop_requested = True

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
                results.append(result)
                if self._disabled:
                    break
                continue

            self._ensure_schema_version(result.schema_version)
            self._register_action(request.action_type)
            enriched_audit = dict(result.audit)
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
            )
            if self._is_critical_result(result):
                self._record_critical_error("critical_action_result")
            self.event_bus.publish("action.completed", result)
            results.append(result)
            if self._disabled:
                break

        return results

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
        return list(self._recent_actions)[-(threshold - 1) :] == [action_type] * (threshold - 1)

    def _is_critical_result(self, result: ActionResult) -> bool:
        if result.success:
            return False
        policy = result.audit.get("policy") if isinstance(result.audit, dict) else None
        if isinstance(policy, dict) and policy.get("risk_level") == "critical":
            return True
        if isinstance(result.error, str) and "critical" in result.error.lower():
            return True
        return bool(result.audit.get("critical_error", False)) if isinstance(result.audit, dict) else False

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
