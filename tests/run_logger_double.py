"""In-memory test double for the logger used by the life loop."""

from __future__ import annotations

from typing import Any


class RecordingRunLogger:
    """Implement the ``RunLogger`` surface consumed by ``life.loop``.

    Unlike the production logger, this double never opens or writes a file.
    Every logging call is retained in :attr:`calls` as a small dictionary so a
    test can inspect emitted events without knowing anything about persistence.
    """

    def __init__(self, run_id: str, **_: Any) -> None:
        self.run_id = run_id
        self.calls: list[dict[str, Any]] = []
        self.reputation: dict[str, dict[str, float | int]] = {}

    def __enter__(self) -> "RecordingRunLogger":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        return False

    def _record(self, method: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append({"method": method, "args": args, "kwargs": kwargs})

    def log(self, *args: Any, **kwargs: Any) -> None:
        self._record("log", *args, **kwargs)

    def log_event(self, event: str, **info: Any) -> None:
        self._record("log_event", event, **info)

    def log_interaction(self, event: str, **info: Any) -> None:
        self._record("log_interaction", event, **info)

    def log_death(self, reason: str, **info: Any) -> None:
        self._record("log_death", reason, **info)

    def log_consciousness(self, *args: Any, **kwargs: Any) -> None:
        self._record("log_consciousness", *args, **kwargs)

    def log_phase_metrics(self, *args: Any, **kwargs: Any) -> None:
        self._record("log_phase_metrics", *args, **kwargs)

    def log_refusal(self, skill: str) -> None:
        self._record("log_refusal", skill)

    def log_delay(self, skill: str, resume_at: float) -> None:
        self._record("log_delay", skill, resume_at)

    def log_absurde(self, skill: str, diff: str) -> None:
        self._record("log_absurde", skill, diff)

    def log_test_coevolution(self, *args: Any, **kwargs: Any) -> None:
        self._record("log_test_coevolution", *args, **kwargs)

    def skill_reputation(self) -> dict[str, dict[str, float | int]]:
        return self.reputation
