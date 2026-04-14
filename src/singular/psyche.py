"""Simple modeling of mood and behavioural traits."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, ClassVar
from pathlib import Path
import random
from enum import Enum

from .memory import read_psyche, write_psyche
from .motivation import GoalPolicy, Objective
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
    sleeping: bool = False
    objectives: Dict[str, Objective] = field(default_factory=dict)
    social_states: Dict[str, Dict[str, float]] = field(default_factory=dict)
    schema_version: int = field(default=3, init=False)
    mood_history: list[str] = field(default_factory=list)

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

    _SOCIAL_KEYS: ClassVar[tuple[str, ...]] = (
        "gratitude",
        "loyalty",
        "jealousy",
        "resentment",
    )

    _SOCIAL_EVENT_DELTAS: Dict[str, Dict[str, float]] = field(
        default_factory=lambda: {
            "help.completed": {
                "gratitude": 0.20,
                "loyalty": 0.10,
                "jealousy": -0.05,
                "resentment": -0.10,
            },
            "competition.lost": {
                "gratitude": -0.05,
                "loyalty": -0.05,
                "jealousy": 0.20,
                "resentment": 0.15,
            },
            "betrayal": {
                "gratitude": -0.15,
                "loyalty": -0.25,
                "jealousy": 0.10,
                "resentment": 0.30,
            },
            "share.completed": {
                "gratitude": 0.15,
                "loyalty": 0.15,
                "jealousy": -0.10,
                "resentment": -0.10,
            },
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

    def irrational_decision(
        self, rng: random.Random | None = None
    ) -> "Psyche.Decision":
        """Return the outcome of a potentially irrational choice.

        Depending on the current mood the psyche may decide to refuse the
        action, delay it or accept it.  ``REFUSE`` and ``DELAY`` share the
        irrationality probability while ``ACCEPT`` represents the normal path.
        """

        if rng is None:
            rng = random.Random()
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

    def social_state(self, target_life: str) -> Dict[str, float]:
        """Return social state for ``target_life``, creating defaults if missing."""

        current = self.social_states.get(target_life)
        if not isinstance(current, dict):
            current = {}
        normalized = {
            key: _clamp(float(current.get(key, 0.5))) for key in self._SOCIAL_KEYS
        }
        self.social_states[target_life] = normalized
        return normalized

    def apply_social_interaction(self, target_life: str, interaction: str) -> Dict[str, float]:
        """Apply interaction-triggered social deltas for one target life."""

        state = self.social_state(target_life)
        for key, delta in self._SOCIAL_EVENT_DELTAS.get(interaction, {}).items():
            state[key] = _clamp(state[key] + delta)
        return state

    def cooperation_score(self, target_life: str) -> float:
        """Return willingness to cooperate with ``target_life`` in ``[0, 1]``."""

        state = self.social_state(target_life)
        trait_base = (self.optimism + self.resilience + self.patience) / 3.0
        social_signal = (
            0.35 * state["gratitude"]
            + 0.35 * state["loyalty"]
            - 0.20 * state["jealousy"]
            - 0.30 * state["resentment"]
        )
        return _clamp((0.6 * trait_base) + (0.4 * _clamp(0.5 + social_signal)))

    def reproduction_arbitration_score(self, base_score: float, target_life: str) -> float:
        """Modulate reproduction arbitration score using social emotions."""

        state = self.social_state(target_life)
        affect = _clamp(
            0.5
            + (0.25 * state["loyalty"])
            + (0.15 * state["gratitude"])
            - (0.20 * state["resentment"])
            - (0.10 * state["jealousy"])
        )
        return _clamp((0.7 * _clamp(base_score)) + (0.3 * affect))

    def relational_risk_tolerance(self, target_life: str) -> float:
        """Return tolerated relational risk level for ``target_life`` in ``[0, 1]``."""

        state = self.social_state(target_life)
        trait_base = (self.playfulness + self.optimism) / 2.0
        social_adjustment = (
            0.15 * state["gratitude"]
            + 0.10 * state["loyalty"]
            + 0.05 * state["jealousy"]
            - 0.25 * state["resentment"]
        )
        return _clamp(trait_base + social_adjustment)

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
        self.mood_history.append(mood.value)
        if len(self.mood_history) > 256:
            self.mood_history = self.mood_history[-256:]

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
        """Clamp and rebalance objective weights for arbitration."""
        modulation = self.goal_modulation_profile()
        for name, obj in self.objectives.items():
            horizon_boost = 0.0
            if obj.horizon_ticks is not None:
                horizon_boost = 0.15 if obj.horizon_ticks <= 10 else -0.05
            parent_boost = 0.0
            if obj.parent and obj.parent in self.objectives:
                parent_boost = self.objectives[obj.parent].weight * 0.1
            policy_signal = obj.arbitration_score()
            obj.weight = _clamp(
                obj.weight * modulation
                + horizon_boost
                + parent_boost
                + (policy_signal - 0.5) * 0.2
            )

    def goal_modulation_profile(self) -> float:
        """Return a modulation factor derived from mood and recent history."""
        mood = self.last_mood or Mood.NEUTRAL
        mood_factor = {
            Mood.PROUD: 1.08,
            Mood.CURIOUS: 1.05,
            Mood.PLEASURE: 1.06,
            Mood.FRUSTRATED: 0.92,
            Mood.ANXIOUS: 0.95,
            Mood.PAIN: 0.9,
            Mood.FATIGUE: 0.88,
        }.get(mood, 1.0)
        if not self.objectives:
            return mood_factor
        reward_signal = sum(obj.reward for obj in self.objectives.values()) / max(
            len(self.objectives), 1
        )
        reward_factor = 1.0 + max(-0.1, min(0.1, reward_signal * 0.05))
        return max(0.7, min(1.3, mood_factor * reward_factor))

    def objective_weights(self) -> Dict[str, float]:
        """Return normalized objective weights after modulation."""
        self.adjust_objectives()
        if not self.objectives:
            return {}
        total = sum(max(0.0, obj.weight) for obj in self.objectives.values())
        if total <= 0:
            total = float(len(self.objectives))
        return {
            name: max(0.0, obj.weight) / total for name, obj in self.objectives.items()
        }

    def weighted_objective_axes(self) -> dict[str, float]:
        """Map objective policies to reflection axes."""
        if not self.objectives:
            return {"long_term": 0.33, "sandbox": 0.33, "resource": 0.34}
        normalized = self.objective_weights()
        long_term = 0.0
        sandbox = 0.0
        resource = 0.0
        for name, obj in self.objectives.items():
            w = normalized.get(name, 0.0)
            policy = obj.policy
            long_term += w * (0.6 * policy.priorite + 0.4 * policy.alignement_valeurs)
            sandbox += w * (0.7 * policy.urgence + 0.3 * policy.besoin)
            resource += w * (0.6 * policy.besoin + 0.4 * (1.0 - policy.urgence))
        total = long_term + sandbox + resource
        if total <= 0.0:
            return {"long_term": 0.33, "sandbox": 0.33, "resource": 0.34}
        return {
            "long_term": long_term / total,
            "sandbox": sandbox / total,
            "resource": resource / total,
        }

    def operator_bias(self, operator_names: list[str]) -> Dict[str, float]:
        """Return operator bias from objective hierarchy and horizon pressure."""
        if not operator_names:
            return {}
        weights = self.objective_weights()
        if not weights:
            return {}
        horizon_pressure = sum(
            1.0
            for obj in self.objectives.values()
            if obj.horizon_ticks is not None and obj.horizon_ticks <= 10
        ) / max(1, len(self.objectives))
        ordered = list(operator_names)
        midpoint = max(1, len(ordered) - 1)
        biases: Dict[str, float] = {}
        ambition = sum(
            weights.get(name, 0.0) * obj.policy.priorite
            for name, obj in self.objectives.items()
        )
        urgency = sum(
            weights.get(name, 0.0) * obj.policy.urgence
            for name, obj in self.objectives.items()
        )
        for index, name in enumerate(ordered):
            exploit_index = 1.0 - (index / midpoint)
            biases[name] = (ambition * exploit_index * 0.2) + (
                urgency * horizon_pressure * (1.0 - exploit_index) * 0.2
            )
        return biases

    # Exposed helpers -----------------------------------------------------
    def interaction_policy(self, target_life: str | None = None) -> str:
        """Return the interaction policy based on mood and traits."""
        if target_life is not None:
            cooperation = self.cooperation_score(target_life)
            if cooperation >= 0.65:
                return "engaging"
            if cooperation <= 0.35:
                return "cautious"
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

    def sleep_tick(self, amount: float = 5.0) -> float:
        """Regenerate energy while sleeping without altering traits.

        Parameters
        ----------
        amount:
            Energy to recover during this tick.  Energy is capped at ``100``.

        Returns
        -------
        float
            The new energy level after regeneration.
        """

        self.energy = min(100.0, self.energy + amount)
        return self.energy

    # Persistence helpers -------------------------------------------------
    def save_state(self, path: Path | str | None = None) -> None:
        """Persist current psyche state to disk."""
        state: Dict[str, Any] = {
            "schema_version": self.schema_version,
            "curiosity": self.curiosity,
            "patience": self.patience,
            "playfulness": self.playfulness,
            "optimism": self.optimism,
            "resilience": self.resilience,
            "energy": self.energy,
            "last_mood": self.last_mood.value if self.last_mood else None,
            "mood_history": list(self.mood_history),
            "social_states": {
                target: {
                    key: _clamp(float(values.get(key, 0.5)))
                    for key in self._SOCIAL_KEYS
                }
                for target, values in self.social_states.items()
                if isinstance(values, dict)
            },
        }
        if self.objectives:
            state["objectives"] = {
                name: {
                    "weight": obj.weight,
                    "reward": obj.reward,
                    "parent": obj.parent,
                    "horizon_ticks": obj.horizon_ticks,
                    "policy": {
                        "besoin": obj.policy.besoin,
                        "priorite": obj.policy.priorite,
                        "urgence": obj.policy.urgence,
                        "alignement_valeurs": obj.policy.alignement_valeurs,
                    },
                }
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
        objectives_payload = data.get("objectives", {})
        if not isinstance(objectives_payload, dict):
            objectives_payload = {}
        mood_history = data.get("mood_history", [])
        schema_version = int(data.get("schema_version", 1))
        social_payload = data.get("social_states", {})
        if not isinstance(social_payload, dict):
            social_payload = {}
        if not isinstance(mood_history, list):
            mood_history = []

        def _policy_from(payload: dict[str, Any]) -> GoalPolicy:
            policy_payload = payload.get("policy")
            if not isinstance(policy_payload, dict):
                policy_payload = {}
            return GoalPolicy(
                besoin=float(policy_payload.get("besoin", 0.5)),
                priorite=float(policy_payload.get("priorite", 0.5)),
                urgence=float(policy_payload.get("urgence", 0.5)),
                alignement_valeurs=float(policy_payload.get("alignement_valeurs", 0.5)),
            )

        psyche = cls(
            curiosity=data.get("curiosity", 0.5),
            patience=data.get("patience", 0.5),
            playfulness=data.get("playfulness", 0.5),
            optimism=data.get("optimism", 0.5),
            resilience=data.get("resilience", 0.5),
            energy=data.get("energy", 100.0),
            objectives={
                name: Objective(
                    name=name,
                    weight=float(obj.get("weight", 1.0)),
                    reward=float(obj.get("reward", 0.0)),
                    parent=obj.get("parent"),
                    horizon_ticks=obj.get("horizon_ticks"),
                    policy=_policy_from(obj),
                )
                for name, obj in objectives_payload.items()
                if isinstance(obj, dict)
            },
            social_states={
                str(target): {
                    key: _clamp(float(values.get(key, 0.5)))
                    for key in cls._SOCIAL_KEYS
                }
                for target, values in social_payload.items()
                if isinstance(values, dict)
            },
            mood_history=[str(entry) for entry in mood_history[-256:]],
        )
        mood_val = data.get("last_mood")
        psyche.last_mood = Mood(mood_val) if mood_val else None
        psyche.schema_version = max(3, schema_version)
        return psyche
