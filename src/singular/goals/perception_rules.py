from __future__ import annotations

from typing import Any, Mapping

RULESET_VERSION = "2026-04-14.v1"

SYSTEM_DECISION_DELTAS: dict[str, dict[str, float]] = {
    "reduce_mutation_cadence": {
        "efficacite": -0.04,
        "robustesse": 0.08,
        "exploration": -0.05,
    },
    "delay_heavy_synthesis": {
        "efficacite": -0.03,
        "robustesse": 0.06,
        "exploration": -0.04,
    },
    "prioritize_memory_compaction": {
        "robustesse": 0.09,
        "efficacite": 0.03,
        "exploration": -0.03,
    },
    "trigger_economy_mode": {
        "robustesse": 0.12,
        "efficacite": -0.05,
        "exploration": -0.08,
    },
}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_tech_debt_markers(
    perception_signals: Mapping[str, Any],
) -> tuple[float | None, float | None]:
    artifact_events = perception_signals.get("artifact_events")
    latest: float | None = None
    if isinstance(artifact_events, list):
        for entry in artifact_events:
            if not isinstance(entry, Mapping):
                continue
            if str(entry.get("type")) != "artifact.tech_debt.simple":
                continue
            payload = entry.get("data")
            if isinstance(payload, Mapping):
                latest = _float(payload.get("markers"), default=0.0)

    previous_candidates = (
        perception_signals.get("tech_debt_previous_markers"),
        perception_signals.get("tech_debt_baseline_markers"),
        perception_signals.get("artifact_tech_debt_previous"),
    )
    previous = next(
        (
            _float(candidate)
            for candidate in previous_candidates
            if candidate is not None
        ),
        None,
    )
    return latest, previous


def _extract_user_friction_index(perception_signals: Mapping[str, Any]) -> float | None:
    for key in ("user_friction", "friction_index"):
        if key in perception_signals:
            return _clamp(_float(perception_signals[key], default=0.0))

    memory = (
        perception_signals.get("episode_memory")
        or perception_signals.get("episodic_memory")
        or perception_signals.get("memory")
    )
    if not isinstance(memory, Mapping):
        return None

    if "user_friction" in memory:
        return _clamp(_float(memory.get("user_friction"), default=0.0))

    if "friction_index" in memory:
        return _clamp(_float(memory.get("friction_index"), default=0.0))

    indicators = memory.get("friction_indicators")
    if isinstance(indicators, Mapping):
        blockers = _float(indicators.get("blockers"), default=0.0)
        complaints = _float(indicators.get("complaints"), default=0.0)
        retries = _float(indicators.get("retry_rate"), default=0.0)
        return _clamp((blockers * 0.4) + (complaints * 0.4) + (retries * 0.2))

    return None


def apply_perception_rules(
    perception_signals: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return deterministic objective deltas derived from perception signals."""

    deltas = {
        "coherence": 0.0,
        "robustesse": 0.0,
        "efficacite": 0.0,
        "exploration": 0.0,
    }
    applied_rules: list[dict[str, Any]] = []

    if not isinstance(perception_signals, Mapping):
        return {
            "version": RULESET_VERSION,
            "deltas": deltas,
            "applied_rules": applied_rules,
        }

    current_markers, previous_markers = _extract_tech_debt_markers(perception_signals)
    if (
        current_markers is not None
        and previous_markers is not None
        and current_markers > previous_markers
    ):
        delta = min(0.16, (current_markers - previous_markers) * 0.02)
        deltas["robustesse"] += delta
        deltas["exploration"] -= delta * 0.35
        applied_rules.append(
            {
                "rule_id": "R-001-tech-debt-up",
                "current_markers": current_markers,
                "previous_markers": previous_markers,
                "delta_robustesse": delta,
            }
        )

    friction = _extract_user_friction_index(perception_signals)
    if friction is not None:
        if friction >= 0.5:
            scaled = (friction - 0.5) * 2.0
            coherence_delta = 0.04 + (0.10 * scaled)
            efficacite_delta = 0.03 + (0.08 * scaled)
            deltas["coherence"] += coherence_delta
            deltas["efficacite"] += efficacite_delta
            deltas["exploration"] -= (coherence_delta + efficacite_delta) * 0.4
            applied_rules.append(
                {
                    "rule_id": "R-002-user-friction-high",
                    "friction": friction,
                    "delta_coherence": coherence_delta,
                    "delta_efficacite": efficacite_delta,
                }
            )
        else:
            boost = (0.5 - friction) * 0.04
            deltas["exploration"] += boost
            applied_rules.append(
                {
                    "rule_id": "R-003-user-friction-low",
                    "friction": friction,
                    "delta_exploration": boost,
                }
            )

    perception_decisions = perception_signals.get("perception_decisions")
    if isinstance(perception_decisions, list):
        for decision_entry in perception_decisions:
            if not isinstance(decision_entry, Mapping):
                continue
            decision = str(decision_entry.get("decision", ""))
            decision_deltas = SYSTEM_DECISION_DELTAS.get(decision)
            if not decision_deltas:
                continue
            for objective, delta in decision_deltas.items():
                deltas[objective] += delta
            applied_rules.append(
                {
                    "rule_id": f"R-010-system-{decision}",
                    "decision": decision,
                    "perception": decision_entry.get("perception"),
                    "source_metric": decision_entry.get("source_metric"),
                    "source_value": decision_entry.get("source_value"),
                    "source_threshold": decision_entry.get("source_threshold"),
                    "deltas": dict(decision_deltas),
                }
            )

    return {
        "version": RULESET_VERSION,
        "deltas": deltas,
        "applied_rules": applied_rules,
    }
