from __future__ import annotations

from typing import TypedDict


class TimelineItem(TypedDict, total=False):
    timestamp: str | None
    life: str
    operator: str | None
    accepted: bool | None
    impact: str
    impact_delta: float | None
    score_base: float | None
    score_new: float | None
    run: str | None
