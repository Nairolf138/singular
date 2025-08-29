"""Simple notification helpers."""

from __future__ import annotations

from typing import Callable


def notify(message: str, channel: Callable[[str], None] | None = None) -> None:
    """Send *message* through *channel*.

    By default messages are printed to standard output. A different callable
    can be provided via *channel* (for example ``logging.getLogger(__name__).info``).
    """

    (channel or print)(message)
