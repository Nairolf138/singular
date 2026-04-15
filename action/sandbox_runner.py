"""Controlled execution layer for UI-like agent actions.

This module intentionally disallows arbitrary shell execution and only supports a
small typed catalog of actions.
"""

from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from threading import Event
from time import monotonic
from typing import Any, Callable, Deque, Dict, Literal, Mapping, MutableMapping


AllowedActionName = str
Rollback = Callable[[], None]
RunnerMode = Literal["ghost", "live"]


class ActionError(RuntimeError):
    """Base error for sandboxed actions."""


class ActionTimeoutError(ActionError):
    """Raised when one action exceeds the timeout."""


class ActionRateLimitError(ActionError):
    """Raised when rate limits are exceeded."""


class CancellationError(ActionError):
    """Raised when execution has been cancelled."""


class CircuitBreakerOpenError(ActionError):
    """Raised when the runner is in open circuit-breaker state."""


@dataclass(slots=True)
class RunnerConfig:
    timeout_s: float = 2.0
    rate_limit_count: int = 20
    rate_limit_window_s: float = 10.0
    max_consecutive_failures: int = 3
    circuit_open_s: float = 15.0
    initial_mode: RunnerMode = "ghost"
    require_qa_before_live: bool = True


class DefaultActionBackend:
    """Thin backend contract.

    Replace these methods with real integrations (desktop automation, webdriver,
    etc.) in production.
    """

    def click(self, *, x: int, y: int, button: str = "left") -> dict[str, Any]:
        return {"ok": True, "action": "click", "x": x, "y": y, "button": button}

    def type(self, *, text: str, clear: bool = False) -> dict[str, Any]:
        return {"ok": True, "action": "type", "chars": len(text), "clear": clear}

    def hotkey(self, *, keys: list[str]) -> dict[str, Any]:
        return {"ok": True, "action": "hotkey", "keys": keys}

    def open_app(self, *, app: str, args: list[str] | None = None) -> dict[str, Any]:
        return {"ok": True, "action": "open_app", "app": app, "args": args or []}

    def read_clipboard(self) -> dict[str, Any]:
        return {"ok": True, "action": "read_clipboard", "text": ""}


@dataclass(slots=True)
class SandboxRunner:
    backend: DefaultActionBackend
    config: RunnerConfig = field(default_factory=RunnerConfig)
    _timestamps: Deque[float] = field(default_factory=deque, init=False)
    _cancel_event: Event = field(default_factory=Event, init=False)
    _consecutive_failures: int = field(default=0, init=False)
    _circuit_open_until: float = field(default=0.0, init=False)
    _rollbacks: list[Rollback] = field(default_factory=list, init=False)
    _catalog: MutableMapping[AllowedActionName, Callable[..., Any]] = field(
        default_factory=dict, init=False
    )
    _mode: RunnerMode = field(default="ghost", init=False)
    _qa_completed: bool = field(default=False, init=False)
    _ghost_log: list[dict[str, Any]] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self._mode = self.config.initial_mode
        self._catalog = {
            "click": self.backend.click,
            "type": self.backend.type,
            "hotkey": self.backend.hotkey,
            "open_app": self.backend.open_app,
            "read_clipboard": self.backend.read_clipboard,
        }

    @property
    def allowed_actions(self) -> tuple[str, ...]:
        return tuple(self._catalog.keys())

    @property
    def mode(self) -> RunnerMode:
        return self._mode

    @property
    def ghost_log(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._ghost_log)

    def run_qa_plan(self, steps: list[Mapping[str, Any]]) -> list[Any]:
        previous_mode = self._mode
        try:
            self._mode = "ghost"
            results = self.run_plan(steps)
            self._qa_completed = True
            return results
        finally:
            self._mode = previous_mode

    def enable_live_mode(self) -> None:
        if self.config.require_qa_before_live and not self._qa_completed:
            raise ActionError("live mode requires a successful QA step in ghost mode")
        self._mode = "live"

    def cancel(self) -> None:
        self._cancel_event.set()

    def reset_cancellation(self) -> None:
        self._cancel_event.clear()

    def run_action(self, action: str, params: Mapping[str, Any] | None = None) -> Any:
        params = dict(params or {})
        if self._mode == "live" and self.config.require_qa_before_live and not self._qa_completed:
            raise ActionError("live mode requires a successful QA step in ghost mode")

        self._ensure_circuit_closed()
        self._ensure_not_cancelled()
        self._check_rate_limit()

        handler = self._catalog.get(action)
        if handler is None:
            raise ActionError(
                f"action '{action}' not allowed; allowed actions: {', '.join(self.allowed_actions)}"
            )

        start = monotonic()
        try:
            if self._mode == "ghost":
                result = self._simulate_action(action, params)
            else:
                result = self._run_with_timeout(handler, params)
                self._register_rollback(action, params)
        except Exception:
            self._record_failure()
            self._rollback_best_effort()
            raise

        elapsed = monotonic() - start
        if elapsed > self.config.timeout_s:
            self._record_failure()
            self._rollback_best_effort()
            raise ActionTimeoutError(
                f"action '{action}' exceeded strict timeout ({self.config.timeout_s}s)"
            )

        self._consecutive_failures = 0
        return result

    def run_plan(self, steps: list[Mapping[str, Any]]) -> list[Any]:
        results: list[Any] = []
        for step in steps:
            action = str(step["action"])
            params = dict(step.get("params") or {})
            results.append(self.run_action(action, params))
        return results

    def _run_with_timeout(self, handler: Callable[..., Any], params: Dict[str, Any]) -> Any:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(handler, **params)
            try:
                return future.result(timeout=self.config.timeout_s)
            except FutureTimeout as exc:
                future.cancel()
                raise ActionTimeoutError("action timed out") from exc

    def _simulate_action(self, action: str, params: Mapping[str, Any]) -> dict[str, Any]:
        simulated = {
            "ok": True,
            "simulated": True,
            "action": action,
            "params": dict(params),
            "overlay": f"[ghost] would execute action '{action}' with params={dict(params)}",
        }
        self._ghost_log.append(simulated)
        return simulated

    def _check_rate_limit(self) -> None:
        now = monotonic()
        window_start = now - self.config.rate_limit_window_s
        while self._timestamps and self._timestamps[0] < window_start:
            self._timestamps.popleft()

        if len(self._timestamps) >= self.config.rate_limit_count:
            raise ActionRateLimitError(
                "rate limit reached: "
                f"max {self.config.rate_limit_count} actions every {self.config.rate_limit_window_s}s"
            )
        self._timestamps.append(now)

    def _ensure_not_cancelled(self) -> None:
        if self._cancel_event.is_set():
            raise CancellationError("runner cancelled")

    def _ensure_circuit_closed(self) -> None:
        now = monotonic()
        if now < self._circuit_open_until:
            raise CircuitBreakerOpenError("circuit breaker open")

    def _record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.config.max_consecutive_failures:
            self._circuit_open_until = monotonic() + self.config.circuit_open_s

    def _register_rollback(self, action: str, params: Mapping[str, Any]) -> None:
        if action == "open_app":
            self._rollbacks.append(lambda: self.backend.hotkey(keys=["alt", "f4"]))
        elif action == "type" and params.get("clear"):
            self._rollbacks.append(lambda: self.backend.hotkey(keys=["ctrl", "z"]))

    def _rollback_best_effort(self) -> None:
        while self._rollbacks:
            rollback = self._rollbacks.pop()
            try:
                rollback()
            except Exception:
                continue
