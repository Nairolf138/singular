"""Philosophical-operational life status contract.

This module intentionally stays separate from :mod:`singular.life.vital`:
``compute_vital_timeline()`` describes observable technical vital state, while
``LifeStatusResult`` carries the life contract exposed to CLI, dashboards, and
reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Mapping, Sequence


class LifeStatus(str, Enum):
    """Authorized philosophical-operational life statuses."""

    NOT_ALIVE_YET = "not_alive_yet"
    FRAGILE = "fragile"
    ALIVE = "alive"
    DYING = "dying"
    EXTINCT = "extinct"


AUTHORIZED_LIFE_STATUSES: tuple[str, ...] = tuple(status.value for status in LifeStatus)


def _status_value(status: LifeStatus | str) -> str:
    return status.value if isinstance(status, LifeStatus) else str(status)


def _computed_at_value(computed_at: datetime | str) -> str:
    if isinstance(computed_at, datetime):
        return computed_at.isoformat()
    return str(computed_at)


@dataclass(frozen=True)
class LifeStatusResult:
    """Portable result for the life contract shown by CLI, dashboards, and reports."""

    status: LifeStatus | str
    score: float
    explanation: str
    signals: Mapping[str, Any] = field(default_factory=dict)
    missing_signals: Sequence[str] = field(default_factory=tuple)
    evidence: Mapping[str, Any] = field(default_factory=dict)
    computed_at: datetime | str = field(default_factory=lambda: datetime.now(UTC))

    def to_payload(self) -> dict[str, Any]:
        """Return a JSON-serializable payload for CLI, dashboard, and report use."""

        return {
            "status": _status_value(self.status),
            "score": float(self.score),
            "explanation": self.explanation,
            "signals": dict(self.signals),
            "missing_signals": list(self.missing_signals),
            "evidence": dict(self.evidence),
            "computed_at": _computed_at_value(self.computed_at),
        }
