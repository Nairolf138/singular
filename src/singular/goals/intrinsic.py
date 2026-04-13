from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping
import json

from singular.memory import _atomic_write_text, get_mem_dir


OBJECTIVE_CATALOGUE = ("coherence", "robustesse", "efficacite", "exploration")


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


@dataclass
class GoalWeights:
    """Weights for the intrinsic objective catalogue."""

    coherence: float = 0.25
    robustesse: float = 0.25
    efficacite: float = 0.25
    exploration: float = 0.25

    def normalized(self) -> GoalWeights:
        values = asdict(self)
        total = sum(max(0.0, float(v)) for v in values.values())
        if total <= 0.0:
            return GoalWeights()
        return GoalWeights(**{name: max(0.0, float(value)) / total for name, value in values.items()})


@dataclass
class GoalState:
    """Persisted goal state with evolution history."""

    tick: int = 0
    weights: GoalWeights = field(default_factory=GoalWeights)
    history: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> GoalState:
        weights_payload = payload.get("weights")
        if isinstance(weights_payload, Mapping):
            weights = GoalWeights(
                coherence=float(weights_payload.get("coherence", 0.25)),
                robustesse=float(weights_payload.get("robustesse", 0.25)),
                efficacite=float(weights_payload.get("efficacite", 0.25)),
                exploration=float(weights_payload.get("exploration", 0.25)),
            ).normalized()
        else:
            weights = GoalWeights()
        history = payload.get("history")
        return cls(
            tick=int(payload.get("tick", 0)),
            weights=weights,
            history=list(history) if isinstance(history, list) else [],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "catalogue": list(OBJECTIVE_CATALOGUE),
            "weights": asdict(self.weights),
            "history": self.history,
        }


class IntrinsicGoals:
    """Manage intrinsic goals and influence multi-objective arbitration."""

    def __init__(self, *, path: Path | None = None, history_limit: int = 2000) -> None:
        self.path = path or (get_mem_dir() / "goals.json")
        self.history_limit = max(10, int(history_limit))
        self.state = self._load_state()

    def _load_state(self) -> GoalState:
        if not self.path.exists():
            return GoalState()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, TypeError, json.JSONDecodeError):
            return GoalState()
        if not isinstance(data, Mapping):
            return GoalState()
        return GoalState.from_dict(data)

    def _save(self) -> None:
        _atomic_write_text(self.path, json.dumps(self.state.to_dict(), ensure_ascii=False))

    def update_tick(
        self,
        *,
        tick: int,
        psyche: Any | None,
        health_score: float | None,
        resources: Mapping[str, float] | None,
    ) -> GoalWeights:
        """Update dynamic weights from psyche/health/resources for one tick."""

        curiosity = _clamp(float(getattr(psyche, "curiosity", 0.5))) if psyche else 0.5
        patience = _clamp(float(getattr(psyche, "patience", 0.5))) if psyche else 0.5
        resilience = _clamp(float(getattr(psyche, "resilience", 0.5))) if psyche else 0.5
        optimism = _clamp(float(getattr(psyche, "optimism", 0.5))) if psyche else 0.5
        playfulness = _clamp(float(getattr(psyche, "playfulness", 0.5))) if psyche else 0.5

        health_norm = _clamp((float(health_score) if health_score is not None else 50.0) / 100.0)
        energy = _clamp(float((resources or {}).get("energy", 50.0)) / 100.0)
        food = _clamp(float((resources or {}).get("food", 50.0)) / 100.0)
        warmth = _clamp(float((resources or {}).get("warmth", 50.0)) / 100.0)
        resource_stability = (energy + food + warmth) / 3.0

        weights = GoalWeights(
            coherence=0.2 + 0.35 * patience + 0.25 * resilience,
            robustesse=0.2 + 0.35 * (1.0 - health_norm) + 0.25 * (1.0 - resource_stability),
            efficacite=0.2 + 0.45 * health_norm + 0.2 * optimism,
            exploration=0.2 + 0.45 * curiosity + 0.2 * playfulness + 0.1 * (1.0 - energy),
        ).normalized()

        self.state.tick = int(tick)
        self.state.weights = weights
        self.state.history.append(
            {
                "tick": int(tick),
                "weights": asdict(weights),
                "signals": {
                    "health": health_norm,
                    "resource_stability": resource_stability,
                    "curiosity": curiosity,
                    "patience": patience,
                    "resilience": resilience,
                    "optimism": optimism,
                    "playfulness": playfulness,
                },
            }
        )
        if len(self.state.history) > self.history_limit:
            self.state.history = self.state.history[-self.history_limit :]
        self._save()
        return weights

    def history(self) -> list[dict[str, Any]]:
        return list(self.state.history)

    def objective_arbitration(
        self,
        *,
        expected_gain: float,
        sandbox_risk: float,
        resource_cost: float,
        novelty: float,
    ) -> float:
        """Compute one arbitration score across all objective axes."""

        w = self.state.weights
        coherence_score = 1.0 - abs(_clamp(expected_gain + 0.5, 0.0, 1.0) - 0.5) * 2.0
        robustesse_score = 1.0 - _clamp(sandbox_risk)
        efficacite_score = 1.0 - _clamp(resource_cost)
        exploration_score = _clamp(novelty)
        return (
            w.coherence * coherence_score
            + w.robustesse * robustesse_score
            + w.efficacite * efficacite_score
            + w.exploration * exploration_score
        )

    def influence_action_hypotheses(self, hypotheses: list[Any]) -> list[dict[str, Any]]:
        """Apply intrinsic-goal influence and return adjusted hypothesis payloads."""

        adjusted: list[dict[str, Any]] = []
        total = len(hypotheses)
        for index, hypothesis in enumerate(hypotheses):
            novelty = 1.0 - (index / max(1, total - 1))
            arbitration = self.objective_arbitration(
                expected_gain=float(getattr(hypothesis, "long_term", 0.0)) - 0.5,
                sandbox_risk=float(getattr(hypothesis, "sandbox_risk", 0.0)),
                resource_cost=float(getattr(hypothesis, "resource_cost", 0.0)),
                novelty=novelty,
            )
            adjusted.append(
                {
                    "action": getattr(hypothesis, "action", ""),
                    "long_term": _clamp(float(getattr(hypothesis, "long_term", 0.0)) * 0.6 + arbitration * 0.6),
                    "sandbox_risk": _clamp(float(getattr(hypothesis, "sandbox_risk", 0.0))),
                    "resource_cost": _clamp(
                        float(getattr(hypothesis, "resource_cost", 0.0))
                        * (0.7 + (1.0 - self.state.weights.efficacite) * 0.3)
                    ),
                }
            )
        return adjusted

    def influence_operator_scores(self, operator_stats: Mapping[str, Mapping[str, float]]) -> dict[str, float]:
        """Return per-operator biases for selector integration."""

        if not operator_stats:
            return {}
        max_count = max(float(stats.get("count", 0.0)) for stats in operator_stats.values())
        if max_count <= 0.0:
            max_count = 1.0

        biases: dict[str, float] = {}
        for name, stats in operator_stats.items():
            count = float(stats.get("count", 0.0))
            reward = float(stats.get("reward", 0.0))
            mean_reward = reward / count if count > 0 else 0.0
            exploration_signal = 1.0 - (count / max_count)
            efficiency_signal = _clamp(mean_reward + 0.5, 0.0, 1.0)
            biases[name] = self.objective_arbitration(
                expected_gain=mean_reward,
                sandbox_risk=0.0,
                resource_cost=count / max_count,
                novelty=exploration_signal,
            ) + self.state.weights.efficacite * efficiency_signal
        return biases
