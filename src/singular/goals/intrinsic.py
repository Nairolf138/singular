from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping
import json

from singular.governance.values import ValueWeights
from singular.memory import _atomic_write_text, get_mem_dir
from singular.goals.perception_rules import apply_perception_rules


OBJECTIVE_CATALOGUE = ("coherence", "robustesse", "efficacite", "exploration")
INTRINSIC_MODULATION_VERSION = "intrinsic-mod-v2"


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _mean_mapping_value(values: Any) -> float:
    if not isinstance(values, Mapping) or not values:
        return 0.0
    sample = [_clamp(_as_float(raw)) for raw in values.values()]
    if not sample:
        return 0.0
    return sum(sample) / len(sample)


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

    def __init__(
        self,
        *,
        path: Path | None = None,
        history_limit: int = 2000,
        value_weights: ValueWeights | None = None,
    ) -> None:
        self.path = path or (get_mem_dir() / "goals.json")
        self.history_limit = max(10, int(history_limit))
        self.value_weights = (value_weights or ValueWeights()).normalized()
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
        perception_signals: Mapping[str, Any] | None = None,
    ) -> GoalWeights:
        """Update dynamic objective weights for one tick.

        Expected `perception_signals` additions (modulation v2):
        - `narrative_indicators.risk_aversion_by_action_family`: dict[str, float] in [0,1]
        - `narrative_indicators.accumulated_confidence_by_action_family`: dict[str, float] in [0,1]
        - `narrative_indicators.accumulated_confidence`: float in [0,1] (fallback when no per-family map)
        - `execution_history.recent_injuries`: float/int count
        - `execution_history.recent_successes`: float/int count
        - `execution_history.repeated_failure_pressure`: float in [0,1]
        """

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
        telemetry_efficiency_penalty = 0.0
        telemetry_quality_pressure = 0.0
        telemetry_failure_pressure = 0.0
        host_environmental_pressure = 0.0
        host_environmental_variance = 0.0
        narrative = (perception_signals or {}).get("narrative_indicators")
        execution_history = (perception_signals or {}).get("execution_history")
        risk_aversion = 0.0
        accumulated_confidence = 0.5
        injuries_pressure = 0.0
        success_boost = 0.0
        repeated_failure_pressure = 0.0
        if isinstance(narrative, Mapping):
            risk_aversion = _mean_mapping_value(narrative.get("risk_aversion_by_action_family"))
            confidence_map = narrative.get("accumulated_confidence_by_action_family")
            if isinstance(confidence_map, Mapping) and confidence_map:
                accumulated_confidence = _mean_mapping_value(confidence_map)
            else:
                accumulated_confidence = _clamp(_as_float(narrative.get("accumulated_confidence", 0.5), default=0.5))
        if isinstance(execution_history, Mapping):
            injuries_pressure = _clamp(_as_float(execution_history.get("recent_injuries", 0.0)) / 5.0)
            success_boost = _clamp(_as_float(execution_history.get("recent_successes", 0.0)) / 6.0)
            repeated_failure_pressure = _clamp(
                _as_float(execution_history.get("repeated_failure_pressure", 0.0), default=0.0)
            )

        skill_reputation = (perception_signals or {}).get("skill_reputation")
        if isinstance(skill_reputation, Mapping) and skill_reputation:
            sample_count = 0.0
            total_cost = 0.0
            total_quality = 0.0
            total_failures = 0.0
            for raw_stats in skill_reputation.values():
                if not isinstance(raw_stats, Mapping):
                    continue
                sample_count += 1.0
                total_cost += float(raw_stats.get("mean_cost", 0.0))
                total_quality += float(raw_stats.get("mean_quality", 0.5))
                total_failures += float(raw_stats.get("recent_failures", 0.0))
            if sample_count > 0:
                mean_cost = total_cost / sample_count
                mean_quality = total_quality / sample_count
                mean_failures = total_failures / sample_count
                telemetry_efficiency_penalty = _clamp(mean_cost / 200.0, 0.0, 1.0)
                telemetry_quality_pressure = _clamp(1.0 - mean_quality, 0.0, 1.0)
                telemetry_failure_pressure = _clamp(mean_failures / 3.0, 0.0, 1.0)

        host_aggregates = (perception_signals or {}).get("host_metrics_aggregates")
        if isinstance(host_aggregates, Mapping):
            rolling = host_aggregates.get("rolling_means", {})
            variance = host_aggregates.get("variance", {})
            if isinstance(rolling, Mapping):
                cpu_roll = rolling.get("cpu_percent")
                ram_roll = rolling.get("ram_used_percent")
                temp_roll = rolling.get("host_temperature_c")
                cpu_pressure = (
                    _clamp(_as_float(cpu_roll.get("20", cpu_roll.get("5", 0.0))) / 100.0)
                    if isinstance(cpu_roll, Mapping)
                    else 0.0
                )
                ram_pressure = (
                    _clamp(_as_float(ram_roll.get("20", ram_roll.get("5", 0.0))) / 100.0)
                    if isinstance(ram_roll, Mapping)
                    else 0.0
                )
                thermal_pressure = (
                    _clamp(_as_float(temp_roll.get("20", temp_roll.get("5", 0.0))) / 95.0)
                    if isinstance(temp_roll, Mapping)
                    else 0.0
                )
                host_environmental_pressure = _clamp(
                    (cpu_pressure * 0.45) + (ram_pressure * 0.35) + (thermal_pressure * 0.2)
                )
            if isinstance(variance, Mapping):
                cpu_variance = _clamp(_as_float(variance.get("cpu_percent", 0.0)) / 400.0)
                ram_variance = _clamp(_as_float(variance.get("ram_used_percent", 0.0)) / 400.0)
                host_environmental_variance = _clamp((cpu_variance + ram_variance) / 2.0)

        base_weights = GoalWeights(
            coherence=0.2
            + 0.35 * patience
            + 0.25 * resilience
            + 0.2 * telemetry_quality_pressure
            + 0.15 * (1.0 - repeated_failure_pressure),
            robustesse=0.2
            + 0.35 * (1.0 - health_norm)
            + 0.25 * (1.0 - resource_stability)
            + 0.2 * telemetry_failure_pressure
            + 0.25 * host_environmental_pressure
            + 0.1 * host_environmental_variance
            + 0.25 * injuries_pressure
            + 0.18 * risk_aversion
            + 0.2 * repeated_failure_pressure,
            efficacite=0.2
            + 0.45 * health_norm
            + 0.2 * optimism
            + 0.35 * telemetry_efficiency_penalty
            + 0.2 * (1.0 - host_environmental_pressure)
            + 0.22 * success_boost
            + 0.15 * accumulated_confidence
            - 0.12 * repeated_failure_pressure,
            exploration=0.2
            + 0.45 * curiosity
            + 0.2 * playfulness
            + 0.1 * (1.0 - energy)
            + 0.18 * accumulated_confidence
            - 0.25 * risk_aversion
            - 0.18 * repeated_failure_pressure,
        )
        modulation = apply_perception_rules(perception_signals)
        deltas = modulation["deltas"]
        weights = GoalWeights(
            coherence=base_weights.coherence + float(deltas["coherence"]),
            robustesse=base_weights.robustesse + float(deltas["robustesse"]),
            efficacite=base_weights.efficacite + float(deltas["efficacite"]),
            exploration=base_weights.exploration + float(deltas["exploration"]),
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
                    "host_environmental_pressure": host_environmental_pressure,
                    "host_environmental_variance": host_environmental_variance,
                    "narrative_risk_aversion": risk_aversion,
                    "narrative_accumulated_confidence": accumulated_confidence,
                    "injuries_pressure": injuries_pressure,
                    "success_boost": success_boost,
                    "repeated_failure_pressure": repeated_failure_pressure,
                    "intrinsic_modulation_version": INTRINSIC_MODULATION_VERSION,
                    "perception_rules_version": modulation["version"],
                    "perception_rule_count": len(modulation["applied_rules"]),
                },
                "perception_rules": modulation,
            }
        )
        if len(self.state.history) > self.history_limit:
            self.state.history = self.state.history[-self.history_limit :]
        self._save()
        return weights

    def history(self) -> list[dict[str, Any]]:
        return list(self.state.history)

    def derive_execution_strategy(
        self, perception_signals: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        """Build runtime strategy knobs from structured + narrative feedback signals.

        Additional `perception_signals` keys (modulation v2):
        - `narrative_indicators.risk_aversion_by_action_family`
        - `narrative_indicators.accumulated_confidence[_by_action_family]`
        - `execution_history.repeated_failure_pressure`
        """

        memory = (perception_signals or {}).get("episode_memory", {})
        structured = memory.get("structured_feedback", {}) if isinstance(memory, Mapping) else {}
        narrative = (perception_signals or {}).get("narrative_indicators")
        execution_history = (perception_signals or {}).get("execution_history")
        frustration = _clamp(_as_float(structured.get("frustration", 0.0))) if isinstance(structured, Mapping) else 0.0
        satisfaction = _clamp(_as_float(structured.get("satisfaction", 0.0))) if isinstance(structured, Mapping) else 0.0
        urgency = _clamp(_as_float(structured.get("urgency", 0.0))) if isinstance(structured, Mapping) else 0.0
        theme = str(structured.get("theme", "general")) if isinstance(structured, Mapping) else "general"
        negative_streak = int(memory.get("negative_feedback_streak", 0)) if isinstance(memory, Mapping) else 0
        risk_aversion = _mean_mapping_value(narrative.get("risk_aversion_by_action_family")) if isinstance(narrative, Mapping) else 0.0
        confidence = 0.5
        if isinstance(narrative, Mapping):
            confidence_map = narrative.get("accumulated_confidence_by_action_family")
            if isinstance(confidence_map, Mapping) and confidence_map:
                confidence = _mean_mapping_value(confidence_map)
            else:
                confidence = _clamp(_as_float(narrative.get("accumulated_confidence", 0.5), default=0.5))
        repeated_failure_penalty = (
            _clamp(_as_float(execution_history.get("repeated_failure_pressure", 0.0)))
            if isinstance(execution_history, Mapping)
            else 0.0
        )

        mode = "balanced"
        if frustration >= 0.6 or negative_streak >= 2 or repeated_failure_penalty >= 0.5 or risk_aversion >= 0.7:
            mode = "cautious"
        elif urgency >= 0.6 and repeated_failure_penalty < 0.45:
            mode = "utility_focused"
        elif satisfaction >= 0.75 and confidence >= 0.55:
            mode = "exploratory"

        return {
            "mode": mode,
            "frustration": frustration,
            "satisfaction": satisfaction,
            "urgency": urgency,
            "theme": theme,
            "negative_feedback_streak": negative_streak,
            "risk_aversion": risk_aversion,
            "confidence": confidence,
            "repeated_failure_penalty": repeated_failure_penalty,
            "intrinsic_modulation_version": INTRINSIC_MODULATION_VERSION,
        }

    def adjust_routine_priorities(
        self,
        routines: list[dict[str, Any]],
        *,
        perception_signals: Mapping[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """Adjust routine priorities in-place for the next ACTION window."""

        strategy = self.derive_execution_strategy(perception_signals)
        mode = strategy["mode"]
        theme = str(strategy["theme"])
        urgency = float(strategy["urgency"])
        frustration = float(strategy["frustration"])

        adjusted: list[dict[str, Any]] = []
        for routine in routines:
            payload = dict(routine)
            base = int(payload.get("priority", 50))
            priority = base
            routine_id = str(payload.get("id", "")).lower()
            prompt = str(payload.get("prompt", "")).lower()
            if mode == "cautious":
                priority += int(10 + frustration * 20)
                if any(token in routine_id or token in prompt for token in ("check", "verify", "monitor", "safety")):
                    priority += 8
                if any(token in routine_id or token in prompt for token in ("help", "user", "support", "respond")):
                    priority += int(12 + urgency * 12)
                elif urgency >= 0.6:
                    priority -= int(8 + urgency * 18)
            elif mode == "utility_focused":
                priority += int(6 + urgency * 18)
                if any(token in routine_id or token in prompt for token in ("help", "user", "support", "respond")):
                    priority += 12
            elif mode == "exploratory":
                if any(token in routine_id or token in prompt for token in ("research", "explore", "discover")):
                    priority += 14
                else:
                    priority -= 4
            if theme != "general" and theme in f"{routine_id} {prompt}":
                priority += 10
            payload["priority"] = max(0, priority)
            adjusted.append(payload)
        adjusted.sort(key=lambda item: -int(item.get("priority", 0)))
        return adjusted

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
        v = self.value_weights
        coherence_score = 1.0 - abs(_clamp(expected_gain + 0.5, 0.0, 1.0) - 0.5) * 2.0
        robustesse_score = 1.0 - _clamp(sandbox_risk * (1.0 + v.securite * 0.5))
        efficacite_score = (1.0 - _clamp(resource_cost)) * (0.7 + 0.3 * v.utilite_utilisateur)
        exploration_score = _clamp(novelty) * (0.3 + 0.7 * v.curiosite_bornee)
        arbitration = (
            w.coherence * coherence_score
            + w.robustesse * robustesse_score
            + w.efficacite * efficacite_score
            + w.exploration * exploration_score
        )
        preservation_bonus = v.preservation_memoire * (1.0 - _clamp(resource_cost))
        utility_bonus = v.utilite_utilisateur * _clamp(expected_gain + 0.5, 0.0, 1.0)
        return arbitration + 0.15 * preservation_bonus + 0.1 * utility_bonus

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

    def influence_operator_scores(
        self,
        operator_stats: Mapping[str, Mapping[str, float]],
        skill_reputation: Mapping[str, Mapping[str, float | int]] | None = None,
    ) -> dict[str, float]:
        """Return per-operator biases using objective weights and usage telemetry."""

        if not operator_stats:
            return {}
        max_count = max(float(stats.get("count", 0.0)) for stats in operator_stats.values())
        if max_count <= 0.0:
            max_count = 1.0
        reputation_cost = 0.0
        reputation_failures = 0.0
        reputation_quality = 0.0
        reputation_samples = 0.0
        if skill_reputation:
            for stats in skill_reputation.values():
                reputation_cost += float(stats.get("mean_cost", 0.0))
                reputation_failures += float(stats.get("recent_failures", 0.0))
                reputation_quality += float(stats.get("mean_quality", 0.0))
                reputation_samples += 1.0
        mean_reputation_cost = reputation_cost / reputation_samples if reputation_samples else 0.0
        mean_reputation_quality = reputation_quality / reputation_samples if reputation_samples else 0.5
        reputation_failure_penalty = _clamp(reputation_failures / max(reputation_samples, 1.0) / 3.0, 0.0, 1.0)

        biases: dict[str, float] = {}
        for name, stats in operator_stats.items():
            count = float(stats.get("count", 0.0))
            reward = float(stats.get("reward", 0.0))
            mean_reward = reward / count if count > 0 else 0.0
            exploration_signal = 1.0 - (count / max_count)
            efficiency_signal = _clamp(mean_reward + 0.5, 0.0, 1.0)
            telemetry_alignment = _clamp(
                mean_reputation_quality * 0.7 + (1.0 - reputation_failure_penalty) * 0.3
            )
            biases[name] = self.objective_arbitration(
                expected_gain=mean_reward,
                sandbox_risk=reputation_failure_penalty,
                resource_cost=_clamp((count / max_count) * 0.6 + mean_reputation_cost * 0.4),
                novelty=exploration_signal,
            ) + self.state.weights.efficacite * efficiency_signal + self.state.weights.coherence * telemetry_alignment
        return biases
