"""Simple modeling of mood and behavioural traits."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any
from pathlib import Path

from .memory import read_psyche, write_psyche


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    """Clamp ``value`` to the given range.

    Parameters
    ----------
    value:
        Value to clamp.
    minimum:
        Lower bound of the range.
    maximum:
        Upper bound of the range.
    """
    return max(minimum, min(maximum, value))


def derive_mood(record: dict) -> str:
    """Derive a mood from a run ``record``.

    ``record`` is expected to contain the fields produced by
    :class:`~singular.runs.logger.RunLogger`.  The heuristic is intentionally
    simple:

    * If the run ``improved`` a score (``score_new < score_base``), the psyche
      feels ``"proud"``.
    * If execution became slower (``ms_new`` > ``ms_base``) without improving,
      the psyche is ``"frustrated"``.
    * In all other cases we assume an ``"anxious"`` mood.
    """

    if record.get("improved"):
        return "proud"

    ms_base = record.get("ms_base")
    ms_new = record.get("ms_new")
    if isinstance(ms_base, (int, float)) and isinstance(ms_new, (int, float)):
        if ms_new > ms_base:
            return "frustrated"

    return "anxious"


@dataclass
class Psyche:
    """Represents mutable traits and current mood of an organism.

    The attributes ``curiosity``, ``patience`` and ``playfulness`` are kept in
    the ``[0, 1]`` range and modified according to experienced moods.
    """

    curiosity: float = 0.5
    patience: float = 0.5
    playfulness: float = 0.5

    # ``last_mood`` is updated every time :meth:`feel` is called and can be
    # queried by other subsystems (interaction and mutation policies).
    last_mood: str | None = field(default=None, init=False)

    # Mapping of moods to their effects on the internal traits. The deltas are
    # added after every event and clamped.
    _MOOD_EFFECTS: Dict[str, Dict[str, float]] = field(
        default_factory=lambda: {
            "proud": {"curiosity": 0.1, "patience": 0.05, "playfulness": 0.1},
            "frustrated": {"curiosity": -0.1, "patience": -0.2, "playfulness": -0.1},
            "anxious": {"curiosity": -0.05, "patience": -0.1, "playfulness": -0.05},
            "neutral": {},
        },
        init=False,
        repr=False,
    )

    _INTERACTION_POLICIES: Dict[str, str] = field(
        default_factory=lambda: {
            "proud": "engaging",
            "frustrated": "retry",
            "anxious": "cautious",
            "neutral": "balanced",
        },
        init=False,
        repr=False,
    )

    _MUTATION_POLICIES: Dict[str, str] = field(
        default_factory=lambda: {
            "proud": "exploit",
            "frustrated": "explore",
            "anxious": "analyze",
            "neutral": "default",
        },
        init=False,
        repr=False,
    )

    def process_run_record(self, record: dict) -> None:
        """Process a run ``record`` and persist psyche changes.

        The record is converted to a mood using :func:`derive_mood` and fed to
        :meth:`feel`.  After updating internal traits the state is saved via
        :meth:`save_state` so the psyche persists across sessions.
        """

        self.feel(derive_mood(record))
        self.save_state()

    def feel(self, event: str) -> str:
        """Register an event and update internal state.

        Parameters
        ----------
        event:
            A string describing the event; it is mapped to a mood using
            :attr:`_MOOD_EFFECTS`. If the event is unknown it is treated as
            ``neutral``.

        Returns
        -------
        str
            The mood resulting from the event.
        """
        mood = event.lower()
        if mood not in self._MOOD_EFFECTS:
            mood = "neutral"
        self.last_mood = mood

        for attr, delta in self._MOOD_EFFECTS[mood].items():
            value = getattr(self, attr)
            setattr(self, attr, _clamp(value + delta))

        return mood

    # Exposed helpers -----------------------------------------------------
    def interaction_policy(self) -> str:
        """Return the interaction policy associated with ``last_mood``."""
        mood = self.last_mood or "neutral"
        return self._INTERACTION_POLICIES.get(mood, "balanced")

    def mutation_policy(self) -> str:
        """Return the mutation policy associated with ``last_mood``."""
        mood = self.last_mood or "neutral"
        return self._MUTATION_POLICIES.get(mood, "default")

    # Persistence helpers -------------------------------------------------
    def save_state(self, path: Path | str | None = None) -> None:
        """Persist current psyche state to disk."""
        state: Dict[str, Any] = {
            "curiosity": self.curiosity,
            "patience": self.patience,
            "playfulness": self.playfulness,
            "last_mood": self.last_mood,
        }
        if path is None:
            write_psyche(state)
        else:
            write_psyche(state, Path(path))

    @classmethod
    def load_state(cls, path: Path | str | None = None) -> "Psyche":
        """Load psyche state from disk and return a new instance."""
        if path is None:
            data = read_psyche()
        else:
            data = read_psyche(Path(path))
        psyche = cls(
            curiosity=data.get("curiosity", 0.5),
            patience=data.get("patience", 0.5),
            playfulness=data.get("playfulness", 0.5),
        )
        psyche.last_mood = data.get("last_mood")
        return psyche
