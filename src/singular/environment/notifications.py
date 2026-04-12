"""Simple notification helpers."""

from __future__ import annotations

from typing import Callable, Literal

Level = Literal["info", "warning", "critical"]

_ACTION_BY_LEVEL: dict[Level, str] = {
    "info": "continuer observation",
    "warning": "réduire exploration",
    "critical": "changer opérateurs",
}


def _format_notification(message: str, level: Level, action: str | None = None) -> str:
    """Build a user-facing notification payload with actionable guidance."""

    recommendation = action or _ACTION_BY_LEVEL[level]
    return f"[{level.upper()}] {message} — action recommandée: {recommendation}"


def notify(
    message: str,
    channel: Callable[[str], None] | None = None,
    *,
    level: Level = "info",
    action: str | None = None,
) -> None:
    """Send *message* through *channel*.

    By default messages are printed to standard output. A different callable
    can be provided via *channel* (for example ``logging.getLogger(__name__).info``).
    """

    payload = _format_notification(message=message, level=level, action=action)
    (channel or print)(payload)


def auto_post(
    channel: Callable[[str], None] | None,
    message: str,
    *,
    level: Level = "info",
    action: str | None = None,
) -> None:
    """Automatically post *message* via *channel*.

    This is a thin wrapper over :func:`notify` keeping a channel-first
    signature for convenience when used with partials.
    """

    notify(message, channel=channel, level=level, action=action)
