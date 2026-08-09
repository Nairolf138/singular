from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Iterable, Literal, Mapping

HealthState = Literal["amélioration", "plateau", "dégradation"]
ViabilityAction = Literal["normal", "throttled", "paused", "restored", "operator"]


@dataclass(frozen=True)
class ViabilityDriftConfig:
    """Thresholds for the multi-window, hysteretic viability governor."""

    short_window: int = 3
    medium_window: int = 6
    long_window: int = 12
    degrade_cycles: int = 2
    stable_cycles: int = 4
    drift_threshold: float = 0.12
    recovery_threshold: float = 0.05
    critical_score: float = 0.38


@dataclass
class ViabilityDriftDetector:
    """Escalate preventive controls before sandbox policy is violated.

    Every observation combines health, risk, resources, failure rate, trait
    continuity, useful-skill retention and mutation fitness.  Both a short vs
    long trend and a medium-window absolute level must agree; consequently one
    anomalous sample cannot change the governance state.
    """

    config: ViabilityDriftConfig = field(default_factory=ViabilityDriftConfig)
    action: ViabilityAction = "normal"
    degraded_cycles: int = 0
    stable_cycles: int = 0
    samples: list[dict[str, float]] = field(default_factory=list)

    _LEVELS = ("normal", "throttled", "paused", "restored", "operator")
    _BENEFICIAL = ("health", "resources", "traits", "useful_skills", "fitness")
    _ADVERSE = ("risk", "failure_rate")

    @classmethod
    def from_state(cls, state: Mapping[str, object] | None) -> "ViabilityDriftDetector":
        detector = cls()
        if not isinstance(state, Mapping):
            return detector
        action = state.get("action")
        if action in cls._LEVELS:
            detector.action = action  # type: ignore[assignment]
        detector.degraded_cycles = int(state.get("degraded_cycles", 0))
        detector.stable_cycles = int(state.get("stable_cycles", 0))
        raw = state.get("samples", [])
        if isinstance(raw, list):
            detector.samples = [
                {
                    str(k): float(v)
                    for k, v in item.items()
                    if isinstance(v, (int, float))
                }
                for item in raw[-detector.config.long_window :]
                if isinstance(item, Mapping)
            ]
        return detector

    def to_state(self) -> dict[str, object]:
        return {
            "action": self.action,
            "degraded_cycles": self.degraded_cycles,
            "stable_cycles": self.stable_cycles,
            "samples": self.samples[-self.config.long_window :],
            "diagnostics": self.diagnostics(),
        }

    @staticmethod
    def _mean(items: list[dict[str, float]], key: str) -> float:
        values = [item[key] for item in items if key in item]
        return sum(values) / len(values) if values else 0.0

    def _score(self, item: Mapping[str, float]) -> float:
        good = sum(_clamp(float(item.get(k, 1.0))) for k in self._BENEFICIAL)
        adverse = sum(1.0 - _clamp(float(item.get(k, 0.0))) for k in self._ADVERSE)
        score = (good + adverse) / (len(self._BENEFICIAL) + len(self._ADVERSE))
        # Activity, retained skills and fitness are supporting signals, never a
        # licence to select an organism whose direct health is critical.
        health = _clamp(float(item.get("health", 1.0)))
        risk = _clamp(float(item.get("risk", 0.0)))
        if (
            health <= self.config.critical_score
            or risk >= 1.0 - self.config.critical_score
        ):
            score = min(score, self.config.critical_score)
        return score

    def observe(
        self, metrics: Mapping[str, float]
    ) -> tuple[ViabilityAction, str | None]:
        normalized = {
            key: _clamp(float(metrics.get(key, 0.0)))
            for key in (*self._BENEFICIAL, *self._ADVERSE)
        }
        normalized["score"] = self._score(normalized)
        self.samples.append(normalized)
        self.samples = self.samples[-self.config.long_window :]
        if len(self.samples) < self.config.medium_window:
            return self.action, None

        short = self.samples[-self.config.short_window :]
        medium = self.samples[-self.config.medium_window :]
        long = self.samples
        short_score = self._mean(short, "score")
        medium_score = self._mean(medium, "score")
        long_score = self._mean(long, "score")
        drift = long_score - short_score
        degrading = drift >= self.config.drift_threshold and medium_score < long_score
        critical = short_score <= self.config.critical_score
        recovering = (
            abs(short_score - long_score) <= self.config.recovery_threshold
            and short_score > self.config.critical_score
        )

        if degrading or critical:
            self.degraded_cycles += 1
            self.stable_cycles = 0
            if self.degraded_cycles >= self.config.degrade_cycles:
                previous = self.action
                index = min(self._LEVELS.index(self.action) + 1, len(self._LEVELS) - 1)
                self.action = self._LEVELS[index]  # type: ignore[assignment]
                self.degraded_cycles = 0
                if self.action != previous:
                    return self.action, "drift"
        elif recovering:
            self.stable_cycles += 1
            self.degraded_cycles = 0
            if (
                self.stable_cycles >= self.config.stable_cycles
                and self.action != "normal"
            ):
                self.action = "normal"
                self.stable_cycles = 0
                return self.action, "recovered"
        else:
            self.degraded_cycles = 0
            self.stable_cycles = 0
        return self.action, None

    def diagnostics(self) -> dict[str, object]:
        short = self.samples[-self.config.short_window :]
        long = self.samples[-self.config.long_window :]
        return {
            "state": self.action,
            "mutations_enabled": self.action in {"normal", "throttled"},
            "mutation_interval": (
                2
                if self.action == "throttled"
                else (1 if self.action == "normal" else None)
            ),
            "degraded_cycles": self.degraded_cycles,
            "stable_cycles": self.stable_cycles,
            "samples": len(self.samples),
            "metrics": self.samples[-1] if self.samples else {},
            "windows": {
                "short": self._mean(short, "score"),
                "long": self._mean(long, "score"),
            },
            "thresholds": asdict(self.config),
        }


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
            self.accepted_count / self.total_iterations
            if self.total_iterations
            else 0.0
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
