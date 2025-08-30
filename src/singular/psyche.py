"""Simple modeling of mood and behavioural traits."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any
from pathlib import Path
import random
from enum import Enum

from .memory import read_psyche, write_psyche
from .motivation import Objective
from .resource_manager import ResourceManager


class Mood(Enum):
    """Enumerate all possible moods."""

    PROUD = "proud"
    FRUSTRATED = "frustrated"
    ANXIOUS = "anxious"
    CURIOUS = "curious"
    PLEASURE = "pleasure"
    PAIN = "pain"
    NEUTRAL = "neutral"
    FATIGUE = "fatigue"
    ANGER = "anger"
    LONELY = "lonely"


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


def derive_mood(record: dict) -> Mood:
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
        return Mood.PROUD

    ms_base = record.get("ms_base")
    ms_new = record.get("ms_new")
    if isinstance(ms_base, (int, float)) and isinstance(ms_new, (int, float)):
        if ms_new > ms_base:
            return Mood.FRUSTRATED

    return Mood.ANXIOUS


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
    last_mood: Mood | None = field(default=None, init=False)

    # Mapping of moods to their effects on the internal traits. The deltas are
    # added after every event and clamped.
    _MOOD_EFFECTS: Dict[Mood, Dict[str, float]] = field(
        default_factory=lambda: {
            Mood.PROUD: {
                "curiosity": 0.1,
                "patience": 0.05,
                "playfulness": 0.1,
                "optimism": 0.1,
                "resilience": 0.1,
            },
            Mood.FRUSTRATED: {
                "curiosity": -0.1,
                "patience": -0.2,
                "playfulness": -0.1,
                "optimism": -0.2,
                "resilience": -0.1,
            },
            Mood.ANXIOUS: {
                "curiosity": -0.05,
                "patience": -0.1,
                "playfulness": -0.05,
                "optimism": -0.1,
                "resilience": -0.05,
            },
            Mood.CURIOUS: {
                "curiosity": 0.1,
            },
            Mood.PLEASURE: {
                "optimism": 0.1,
                "resilience": 0.1,
            },
            Mood.PAIN: {
                "optimism": -0.1,
                "resilience": -0.1,
            },
            Mood.NEUTRAL: {},
            Mood.FATIGUE: {
                "curiosity": -0.05,
                "playfulness": -0.05,
                "optimism": -0.1,
            },
            Mood.ANGER: {
                "patience": -0.2,
                "playfulness": -0.1,
                "optimism": -0.1,
            },
            Mood.LONELY: {
                "optimism": -0.1,
                "resilience": -0.1,
            },
        },
        init=False,
        repr=False,
    )

    _INTERACTION_POLICIES: Dict[Mood, str] = field(
        default_factory=lambda: {
            Mood.PROUD: "engaging",
            Mood.FRUSTRATED: "retry",
            Mood.ANXIOUS: "cautious",
            Mood.NEUTRAL: "balanced",
        },
        init=False,
        repr=False,
    )

    _MUTATION_POLICIES: Dict[Mood, str] = field(
        default_factory=lambda: {
            Mood.PROUD: "exploit",
            Mood.FRUSTRATED: "explore",
            Mood.ANXIOUS: "analyze",
            Mood.NEUTRAL: "default",
        },
        init=False,
        repr=False,
    )

    _MUTATION_RATES: Dict[Mood, float] = field(
        default_factory=lambda: {
            Mood.FRUSTRATED: 2.0,
            Mood.ANXIOUS: 0.5,
            Mood.PROUD: 1.2,
            Mood.NEUTRAL: 1.0,
        },
        init=False,
        repr=False,
    )

    _RESOURCE_MOOD_MAP: Dict[str, Mood] = field(
        default_factory=lambda: {
            "tired": Mood.FATIGUE,
            "angry": Mood.ANGER,
            "cold": Mood.LONELY,
            "content": Mood.PLEASURE,
        },
        init=False,
        repr=False,
    )

    @property
    def mutation_rate(self) -> float:
        """Return a mutation rate derived from the latest mood."""
        mood = self.last_mood or Mood.NEUTRAL
        return self._MUTATION_RATES.get(mood, 1.0)

    def update_from_resource_manager(self, rm: ResourceManager) -> Mood:
        """Adjust mood based on ``rm`` resource metrics.

        The :class:`~singular.resource_manager.ResourceManager` exposes a
        :meth:`mood` method returning a list of resource-derived states such as
        ``"tired"`` or ``"angry"``.  Each state is mapped to an internal mood
        via :attr:`_RESOURCE_MOOD_MAP` and processed through :meth:`feel` to
        update :attr:`last_mood` and traits.

        Parameters
        ----------
        rm:
            Resource manager providing energy, food and warmth metrics.

        Returns
        -------
        Mood
            The final mood after processing all resource states.
        """

        moods = rm.mood()
        last: Mood = Mood.NEUTRAL
        for state in moods:
            event = self._RESOURCE_MOOD_MAP.get(state, Mood.NEUTRAL)
            last = self.feel(event)
        return last

    class Decision(Enum):
        """Possible outcomes of an irrational decision."""

        REFUSE = "REFUSE"
        DELAY = "DELAY"
        ACCEPT = "ACCEPT"
        CURIOUS = "CURIOUS"

    def irrational_decision(self, rng: random.Random | None = None) -> "Psyche.Decision":
        """Return the outcome of a potentially irrational choice.

        Depending on the current mood the psyche may decide to refuse the
        action, delay it or accept it.  ``REFUSE`` and ``DELAY`` share the
        irrationality probability while ``ACCEPT`` represents the normal path.
        """

        rng = rng or random
        mood = self.last_mood or Mood.NEUTRAL
        base = {
            Mood.PROUD: 0.05,
            Mood.FRUSTRATED: 0.3,
            Mood.ANXIOUS: 0.2,
        }.get(mood, 0.1)
        if rng.random() < base:
            return rng.choice([self.Decision.REFUSE, self.Decision.DELAY])
        if rng.random() < self.curiosity * 0.01:
            return self.Decision.CURIOUS
        return self.Decision.ACCEPT

    def process_run_record(self, record: dict) -> None:
        """Process a run ``record`` and persist psyche changes.

        The record is converted to a mood using :func:`derive_mood` and fed to
        :meth:`feel`.  After updating internal traits the state is saved via
        :meth:`save_state` so the psyche persists across sessions.
        """

        self.feel(derive_mood(record))
        self.save_state()

    def feel(self, event: Mood) -> Mood:
        """Register an event and update internal state.

        Parameters
        ----------
        event:
            The mood-inducing event.

        Returns
        -------
        Mood
            The mood resulting from the event.
        """
        mood = event
        if mood not in self._MOOD_EFFECTS:
            mood = Mood.NEUTRAL
        self.last_mood = mood

        for attr, delta in self._MOOD_EFFECTS[mood].items():
            value = getattr(self, attr)
            setattr(self, attr, _clamp(value + delta))

        if mood == Mood.PLEASURE:
            for obj in self.objectives.values():
                obj.apply_delta(0.1)
        elif mood == Mood.PAIN:
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
        mood = self.last_mood or Mood.NEUTRAL
        if self.optimism >= 0.7:
            return "engaging"
        if self.resilience <= 0.3:
            return "cautious"
        return self._INTERACTION_POLICIES.get(mood, "balanced")

    def mutation_policy(self) -> str:
        """Return the mutation policy based on mood and traits."""
        mood = self.last_mood or Mood.NEUTRAL
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
            "last_mood": self.last_mood.value if self.last_mood else None,
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
        mood_val = data.get("last_mood")
        psyche.last_mood = Mood(mood_val) if mood_val else None
        return psyche
