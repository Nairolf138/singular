"""Utility functions to evaluate the moral value of actions."""

from __future__ import annotations

from typing import Any, Dict


def score_action(action: str, context: Dict[str, Any] | None = None) -> float:
    """Return a moral score for *action* based on *context*.

    Negative values indicate morally objectionable actions while positive
    values correspond to morally favourable ones. ``context`` may contain a
    mapping ``moral_weights`` associating actions to moral scores.
    """

    context = context or {}
    weights = context.get("moral_weights", {})
    return float(weights.get(action, 0.0))
