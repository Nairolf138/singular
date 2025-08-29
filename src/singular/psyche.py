"""Simple modeling of mood and behavioural traits."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any
from pathlib import Path
import random
from enum import Enum

from .memory import read_psyche, write_psyche
from .motivation import Objective


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

    The attributes ``curiosity``, ``patience``, ``playfulness``, ``optimism`` and
    ``resilience`` are kept in the ``[0, 1]`` range and modified according to
    experienced moods.
    """

    curiosity: float = 0.5
    patience: float = 0.5
    playfulness: float = 0.5
    optimism: float = 0.5
    resilience: float = 0.5
    energy: float = 100.0
    objectives: Dict[str, Objective] = field(default_factory=dict)

    # ``last_mood`` is updated every time :meth:`feel` is called and can be
    # queried by other subsystems (interaction and mutation policies).
    last_mood: str | None = field(default=None, init=False)

    # Mapping of moods to their effects on the internal traits. The deltas are
    # added after every event and clamped.
    _MOOD_EFFECTS: Dict[str, Dict[str, float]] = field(
        default_factory=lambda: {
            "proud": {
                "curiosity": 0.1,
                "patience": 0.05,
                "playfulness": 0.1,
                "optimism": 0.1,
                "resilience": 0.1,
            },
            "frustrated": {
                "curiosity": -0.1,
                "patience": -0.2,
                "playfulness": -0.1,
                "optimism": -0.2,
                "resilience": -0.1,
            },
            "anxious": {
                "curiosity": -0.05,
                "patience": -0.1,
                "playfulness": -0.05,
                "optimism": -0.1,
                "resilience": -0.05,
            },
            "curious": {
                "curiosity": 0.1,
            },
            "pleasure": {
                "optimism": 0.1,
                "resilience": 0.1,
            },
            "pain": {
                "optimism": -0.1,
                "resilience": -0.1,
            },
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

    _MUTATION_RATES: Dict[str, float] = field(
        default_factory=lambda: {
            "frustrated": 2.0,
            "anxious": 0.5,
            "proud": 1.2,
            "neutral": 1.0,
        },
        init=False,
        repr=False,
    )

    @property
    def mutation_rate(self) -> float:
        """Return a mutation rate derived from the latest mood."""
        mood = self.last_mood or "neutral"
        return self._MUTATION_RATES.get(mood, 1.0)

    class Decision(Enum):
        """Possible outcomes of an irrational decision."""

        REFUSE = "REFUSE"
        DELAY = "DELAY"
        ACCEPT = "ACCEPT"

    def irrational_decision(self, rng: random.Random | None = None) -> "Psyche.Decision":
        """Return the outcome of a potentially irrational choice.

        Depending on the current mood the psyche may decide to refuse the
        action, delay it or accept it.  ``REFUSE`` and ``DELAY`` share the
        irrationality probability while ``ACCEPT`` represents the normal path.
        """

        rng = rng or random
        mood = self.last_mood or "neutral"
        base = {
            "proud": 0.05,
            "frustrated": 0.3,
            "anxious": 0.2,
        }.get(mood, 0.1)
        if rng.random() < base:
            return rng.choice([self.Decision.REFUSE, self.Decision.DELAY])
        return self.Decision.ACCEPT

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

        if mood == "pleasure":
            for obj in self.objectives.values():
                obj.apply_delta(0.1)
        elif mood == "pain":
            for obj in self.objectives.values():
                obj.apply_delta(-0.1)
        self.adjust_objectives()

        return mood

    def adjust_objectives(self) -> None:
        """Clamp objective weights to the ``[0, 1]`` range."""
        for obj in self.objectives.values():
            obj.weight = _clamp(obj.weight)

    # Exposed helpers -----------------------------------------------------
    def interaction_policy(self) -> str:
        """Return the interaction policy based on mood and traits."""
        mood = self.last_mood or "neutral"
        if self.optimism >= 0.7:
            return "engaging"
        if self.resilience <= 0.3:
            return "cautious"
        return self._INTERACTION_POLICIES.get(mood, "balanced")

    def mutation_policy(self) -> str:
        """Return the mutation policy based on mood and traits."""
        mood = self.last_mood or "neutral"
        if self.resilience >= 0.7:
            return "exploit"
        if self.optimism <= 0.3:
            return "analyze"
        return self._MUTATION_POLICIES.get(mood, "default")

    # Energy management ---------------------------------------------------
    def consume(self, amount: float = 1.0) -> float:
        """Decrease energy by ``amount`` and return the new value.

        Energy will not drop below ``0``.
        """
        self.energy = max(0.0, self.energy - amount)
        return self.energy

    def gain(self, amount: float = 1.0) -> float:
        """Increase energy by ``amount`` and return the new value."""
        self.energy += amount
        return self.energy

    # Persistence helpers -------------------------------------------------
    def save_state(self, path: Path | str | None = None) -> None:
        """Persist current psyche state to disk."""
        state: Dict[str, Any] = {
            "curiosity": self.curiosity,
            "patience": self.patience,
            "playfulness": self.playfulness,
            "optimism": self.optimism,
            "resilience": self.resilience,
            "energy": self.energy,
            "last_mood": self.last_mood,
        }
        if self.objectives:
            state["objectives"] = {
                name: {"weight": obj.weight, "reward": obj.reward}
                for name, obj in self.objectives.items()
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
            optimism=data.get("optimism", 0.5),
            resilience=data.get("resilience", 0.5),
            energy=data.get("energy", 100.0),
            objectives={
                name: Objective(
                    name,
                    obj.get("weight", 1.0),
                    obj.get("reward", 0.0),
                )
                for name, obj in data.get("objectives", {}).items()
            },
        )
        psyche.last_mood = data.get("last_mood")
        return psyche
