from __future__ import annotations

from typing import Any, List, Tuple


class EpisodicMemory:
    """Simple store for (action, result) pairs."""

    def __init__(self) -> None:
        self._episodes: List[Tuple[Any, Any]] = []

    def remember(self, action: Any, result: Any) -> None:
        """Record the outcome of ``action``."""
        self._episodes.append((action, result))

    def recall(self, action: Any | None = None) -> Any:
        """Return the most recent result for ``action``.

        If ``action`` is ``None``, a list of all stored episodes is returned.
        """
        if action is None:
            return list(self._episodes)
        for past_action, result in reversed(self._episodes):
            if past_action == action:
                return result
        return None
