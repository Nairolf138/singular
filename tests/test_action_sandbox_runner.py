import time

import pytest

from action.sandbox_runner import (
    ActionError,
    ActionRateLimitError,
    ActionTimeoutError,
    CancellationError,
    CircuitBreakerOpenError,
    RunnerConfig,
    SandboxRunner,
)


class SpyBackend:
    def __init__(self):
        self.calls = []

    def click(self, **kwargs):
        self.calls.append(("click", kwargs))
        return {"ok": True}

    def type(self, **kwargs):
        self.calls.append(("type", kwargs))
        return {"ok": True}

    def hotkey(self, **kwargs):
        self.calls.append(("hotkey", kwargs))
        return {"ok": True}

    def open_app(self, **kwargs):
        self.calls.append(("open_app", kwargs))
        return {"ok": True}

    def read_clipboard(self):
        self.calls.append(("read_clipboard", {}))
        return {"ok": True, "text": "hello"}


def test_only_catalog_actions_allowed():
    runner = SandboxRunner(
        backend=SpyBackend(),
        config=RunnerConfig(require_qa_before_live=False, initial_mode="live"),
    )
    with pytest.raises(ActionError):
        runner.run_action("shell", {"cmd": "rm -rf /"})


def test_timeout_is_enforced():
    backend = SpyBackend()

    def slow_click(**kwargs):
        time.sleep(0.08)
        return {"ok": True}

    backend.click = slow_click
    runner = SandboxRunner(
        backend=backend,
        config=RunnerConfig(
            timeout_s=0.02,
            require_qa_before_live=False,
            initial_mode="live",
        ),
    )

    with pytest.raises(ActionTimeoutError):
        runner.run_action("click", {"x": 1, "y": 2})


def test_rate_limit_is_enforced():
    runner = SandboxRunner(
        backend=SpyBackend(),
        config=RunnerConfig(
            rate_limit_count=1,
            rate_limit_window_s=1.0,
            require_qa_before_live=False,
            initial_mode="live",
        ),
    )
    runner.run_action("read_clipboard")
    with pytest.raises(ActionRateLimitError):
        runner.run_action("read_clipboard")


def test_cancellation_stops_execution():
    runner = SandboxRunner(
        backend=SpyBackend(),
        config=RunnerConfig(require_qa_before_live=False, initial_mode="live"),
    )
    runner.cancel()
    with pytest.raises(CancellationError):
        runner.run_action("read_clipboard")


def test_circuit_breaker_opens_after_consecutive_failures():
    backend = SpyBackend()

    def broken_click(**kwargs):
        raise RuntimeError("boom")

    backend.click = broken_click
    runner = SandboxRunner(
        backend=backend,
        config=RunnerConfig(
            max_consecutive_failures=2,
            circuit_open_s=30.0,
            require_qa_before_live=False,
            initial_mode="live",
        ),
    )

    for _ in range(2):
        with pytest.raises(RuntimeError):
            runner.run_action("click", {"x": 1, "y": 1})

    with pytest.raises(CircuitBreakerOpenError):
        runner.run_action("read_clipboard")


def test_open_app_registers_rollback_on_failure():
    backend = SpyBackend()

    def broken_type(**kwargs):
        raise RuntimeError("cannot type")

    backend.type = broken_type

    runner = SandboxRunner(
        backend=backend,
        config=RunnerConfig(require_qa_before_live=False, initial_mode="live"),
    )
    runner.run_action("open_app", {"app": "notepad"})

    with pytest.raises(RuntimeError):
        runner.run_action("type", {"text": "hello"})

    assert ("hotkey", {"keys": ["alt", "f4"]}) in backend.calls


def test_ghost_mode_simulates_and_logs_without_executing_backend():
    backend = SpyBackend()
    runner = SandboxRunner(backend=backend)

    result = runner.run_action("click", {"x": 1, "y": 2})

    assert result["simulated"] is True
    assert result["overlay"].startswith("[ghost] would execute action 'click'")
    assert backend.calls == []
    assert runner.ghost_log[0]["action"] == "click"


def test_live_mode_requires_qa_ghost_step_before_activation():
    runner = SandboxRunner(backend=SpyBackend())

    with pytest.raises(ActionError, match="requires a successful QA step"):
        runner.enable_live_mode()

    qa_results = runner.run_qa_plan([{"action": "read_clipboard"}])
    assert qa_results[0]["simulated"] is True

    runner.enable_live_mode()
    live_result = runner.run_action("read_clipboard")
    assert live_result["ok"] is True
