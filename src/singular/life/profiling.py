"""Lightweight phase profiling helpers for the life loop."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from time import perf_counter
from typing import Iterator, Mapping

DEFAULT_LIFE_LOOP_PHASES: tuple[str, ...] = (
    "mutation",
    "sandbox_scoring",
    "test_runner",
    "coevolution",
    "map_elites",
    "reproduction",
    "checkpoint_write",
    "logging",
)


@dataclass
class PhaseStats:
    """Aggregated timing and cache counters for one named phase."""

    calls: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0

    def add_duration(self, duration_ms: float) -> None:
        self.calls += 1
        self.total_ms += max(0.0, float(duration_ms))
        self.max_ms = max(self.max_ms, max(0.0, float(duration_ms)))

    def add_cache(self, *, hit: bool) -> None:
        if hit:
            self.cache_hits += 1
        else:
            self.cache_misses += 1

    def to_dict(self) -> dict[str, float | int]:
        avg_ms = self.total_ms / self.calls if self.calls else 0.0
        return {
            "calls": self.calls,
            "total_ms": round(self.total_ms, 3),
            "avg_ms": round(avg_ms, 3),
            "max_ms": round(self.max_ms, 3),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
        }


@dataclass
class LifeLoopProfiler:
    """Collect per-tick timings for repeatable life-loop phases."""

    required_phases: tuple[str, ...] = DEFAULT_LIFE_LOOP_PHASES
    stats: dict[str, PhaseStats] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for phase in self.required_phases:
            self.stats.setdefault(phase, PhaseStats())

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        started = perf_counter()
        try:
            yield
        finally:
            self.record_duration(name, (perf_counter() - started) * 1000.0)

    def record_duration(self, name: str, duration_ms: float) -> None:
        self.stats.setdefault(name, PhaseStats()).add_duration(duration_ms)

    def record_cache(self, name: str, *, hit: bool) -> None:
        self.stats.setdefault(name, PhaseStats()).add_cache(hit=hit)

    def merge(self, other: "LifeLoopProfiler") -> None:
        for name, stats in other.stats.items():
            target = self.stats.setdefault(name, PhaseStats())
            target.calls += stats.calls
            target.total_ms += stats.total_ms
            target.max_ms = max(target.max_ms, stats.max_ms)
            target.cache_hits += stats.cache_hits
            target.cache_misses += stats.cache_misses

    def summary(self) -> dict[str, object]:
        phase_payload = {name: self.stats[name].to_dict() for name in sorted(self.stats)}
        total_ms = sum(float(item["total_ms"]) for item in phase_payload.values())
        slowest = None
        if phase_payload:
            slowest = max(
                phase_payload,
                key=lambda name: float(phase_payload[name].get("total_ms", 0.0)),
            )
        return {
            "schema_version": 1,
            "total_ms": round(total_ms, 3),
            "slowest_phase": slowest,
            "phases": phase_payload,
            "cache_candidates": cache_candidates_from_phases(phase_payload),
            "async_distribution_note": (
                "Étudier l'exécution asynchrone/distribuée uniquement après "
                "stabilisation de ces métriques de phase."
            ),
        }


def cache_candidates_from_phases(
    phases: Mapping[str, Mapping[str, object]],
) -> list[dict[str, object]]:
    """Identify repetitive phases where caching can reduce loop cost."""

    candidates: list[dict[str, object]] = []
    sandbox = phases.get("sandbox_scoring", {})
    if int(sandbox.get("cache_hits", 0) or 0) or int(sandbox.get("cache_misses", 0) or 0):
        candidates.append(
            {
                "phase": "sandbox_scoring",
                "reason": "scoring de compétences inchangées réutilisable par empreinte SHA-256 du code",
                "current_cache_hits": int(sandbox.get("cache_hits", 0) or 0),
                "current_cache_misses": int(sandbox.get("cache_misses", 0) or 0),
            }
        )
    config = phases.get("config_loading", {})
    if int(config.get("calls", 0) or 0):
        candidates.append(
            {
                "phase": "config_loading",
                "reason": "chargement de configs répétitif réutilisable par chemin et mtime",
                "current_cache_hits": int(config.get("cache_hits", 0) or 0),
                "current_cache_misses": int(config.get("cache_misses", 0) or 0),
            }
        )
    return candidates
