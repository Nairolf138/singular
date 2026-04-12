from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Literal

HealthState = Literal["amélioration", "plateau", "dégradation"]


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


@dataclass
class HealthSnapshot:
    iteration: int
    score: float
    performance: float
    acceptance_rate: float
    sandbox_stability: float
    energy_resources: float
    failure_frequency: float

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


@dataclass
class HealthTracker:
    """Track and compute organism health as a composite score."""

    total_iterations: int = 0
    accepted_count: int = 0
    failed_count: int = 0
    sandbox_failures: int = 0
    sandbox_checks: int = 0
    latency_ema_ms: float = 0.0
    latency_alpha: float = 0.2

    @classmethod
    def from_state(cls, state: dict[str, float | int] | None) -> HealthTracker:
        if not isinstance(state, dict):
            return cls()
        return cls(
            total_iterations=int(state.get("total_iterations", 0)),
            accepted_count=int(state.get("accepted_count", 0)),
            failed_count=int(state.get("failed_count", 0)),
            sandbox_failures=int(state.get("sandbox_failures", 0)),
            sandbox_checks=int(state.get("sandbox_checks", 0)),
            latency_ema_ms=float(state.get("latency_ema_ms", 0.0)),
            latency_alpha=float(state.get("latency_alpha", 0.2)),
        )

    def to_state(self) -> dict[str, float | int]:
        return {
            "total_iterations": self.total_iterations,
            "accepted_count": self.accepted_count,
            "failed_count": self.failed_count,
            "sandbox_failures": self.sandbox_failures,
            "sandbox_checks": self.sandbox_checks,
            "latency_ema_ms": self.latency_ema_ms,
            "latency_alpha": self.latency_alpha,
        }

    def update(
        self,
        *,
        iteration: int,
        latency_ms: float,
        accepted: bool,
        sandbox_failure: bool,
        energy: float,
        resources: float,
        failed: bool,
    ) -> HealthSnapshot:
        self.total_iterations += 1
        self.accepted_count += int(accepted)
        self.failed_count += int(failed)
        self.sandbox_failures += int(sandbox_failure)
        self.sandbox_checks += 1
        if self.total_iterations == 1:
            self.latency_ema_ms = max(0.0, float(latency_ms))
        else:
            alpha = _clamp(self.latency_alpha)
            self.latency_ema_ms = (
                alpha * max(0.0, float(latency_ms))
                + (1.0 - alpha) * self.latency_ema_ms
            )

        acceptance_rate = (
            self.accepted_count / self.total_iterations if self.total_iterations else 0.0
        )
        sandbox_stability = 1.0 - (
            self.sandbox_failures / self.sandbox_checks if self.sandbox_checks else 0.0
        )
        failure_frequency = (
            self.failed_count / self.total_iterations if self.total_iterations else 0.0
        )
        # Lower latency is better. 100ms -> 0.5, 900ms -> 0.1.
        performance = 1.0 / (1.0 + (self.latency_ema_ms / 100.0))
        energy_norm = _clamp(energy / 5.0)
        resources_norm = _clamp(resources / 5.0)
        energy_resources = (energy_norm + resources_norm) / 2.0

        score = composite_score(
            performance=performance,
            acceptance_rate=acceptance_rate,
            sandbox_stability=sandbox_stability,
            energy_resources=energy_resources,
            failure_frequency=failure_frequency,
        )
        return HealthSnapshot(
            iteration=iteration,
            score=score,
            performance=performance,
            acceptance_rate=acceptance_rate,
            sandbox_stability=sandbox_stability,
            energy_resources=energy_resources,
            failure_frequency=failure_frequency,
        )


def composite_score(
    *,
    performance: float,
    acceptance_rate: float,
    sandbox_stability: float,
    energy_resources: float,
    failure_frequency: float,
) -> float:
    """Compute a weighted health score between 0 and 100."""

    failure_quality = 1.0 - _clamp(failure_frequency)
    value = (
        0.25 * _clamp(performance)
        + 0.20 * _clamp(acceptance_rate)
        + 0.20 * _clamp(sandbox_stability)
        + 0.20 * _clamp(energy_resources)
        + 0.15 * failure_quality
    )
    return round(100.0 * value, 4)


def detect_health_state(
    scores: Iterable[float],
    *,
    short_window: int = 10,
    long_window: int = 50,
    margin: float = 1.0,
) -> HealthState:
    """Compare short and long moving windows to infer health trajectory."""

    values = list(scores)
    if len(values) < max(2, short_window):
        return "plateau"
    short_avg = sum(values[-short_window:]) / min(short_window, len(values))
    long_slice = values[-long_window:] if len(values) >= long_window else values
    long_avg = sum(long_slice) / len(long_slice)
    delta = short_avg - long_avg
    if delta > margin:
        return "amélioration"
    if delta < -margin:
        return "dégradation"
    return "plateau"
