"""Persisted, explicitly uncertain models of other individuals' mental states.

The contents of this store are hypotheses derived from observations.  They are
deliberately kept separate from :mod:`singular.social.graph`: liking somebody
is not evidence that we know what they believe or intend to do.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Callable, Literal, Mapping

from singular.memory import _atomic_write_text, get_mem_dir

SCHEMA_VERSION = 2
_EVIDENCE_LIMIT = 50
EvidenceKind = Literal[
    "direct_observation", "other_statement", "inference", "verified_outcome"
]
_EVIDENCE_KINDS = {
    "direct_observation",
    "other_statement",
    "inference",
    "verified_outcome",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


@dataclass(slots=True)
class MentalStateModel:
    """A versioned hypothesis about one individual, never an asserted fact."""

    individual_id: str
    version: int = 0
    supposed_goals: list[str] = field(default_factory=list)
    intentions: dict[str, float] = field(default_factory=dict)
    attributed_beliefs: dict[str, float] = field(default_factory=dict)
    reliability: float = 0.5
    confidence: float = 0.0
    reciprocity: float = 0.0
    evidence: list[dict[str, object]] = field(default_factory=list)
    uncertainty: float = 1.0
    updated_at: str = field(default_factory=lambda: _utcnow().isoformat())

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class TheoryOfMindStore:
    """JSON-backed collection of independent, per-individual hypotheses."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        clock: Callable[[], datetime] = _utcnow,
        confidence_half_life_days: float = 30.0,
    ) -> None:
        self.path = path or (get_mem_dir() / "theory_of_mind.json")
        self.clock = clock
        self.confidence_half_life_days = max(0.001, confidence_half_life_days)
        self._models: dict[str, MentalStateModel] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        models = raw.get("models", {}) if isinstance(raw, dict) else {}
        if not isinstance(models, dict):
            return
        for individual, value in models.items():
            if not isinstance(individual, str) or not isinstance(value, dict):
                continue
            try:
                self._models[individual] = MentalStateModel(
                    individual_id=individual,
                    version=max(0, int(value.get("version", 0))),
                    supposed_goals=_strings(value.get("supposed_goals")),
                    intentions=_scores(value.get("intentions")),
                    attributed_beliefs=_scores(value.get("attributed_beliefs")),
                    reliability=_clamp(value.get("reliability", 0.5)),
                    confidence=_clamp(value.get("confidence", 0.0)),
                    reciprocity=max(
                        -1.0, min(1.0, float(value.get("reciprocity", 0.0)))
                    ),
                    evidence=_evidence(value.get("evidence")),
                    uncertainty=_clamp(value.get("uncertainty", 1.0)),
                    updated_at=str(value.get("updated_at", self.clock().isoformat())),
                )
            except (TypeError, ValueError):
                continue

    def _save(self) -> None:
        _atomic_write_text(
            self.path,
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "models": {
                        key: model.to_dict()
                        for key, model in sorted(self._models.items())
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
        )

    def get(self, individual_id: str, *, decayed: bool = True) -> dict[str, object]:
        model = self._models.get(
            str(individual_id), MentalStateModel(str(individual_id))
        )
        result = model.to_dict()
        if decayed and model.version:
            try:
                then = datetime.fromisoformat(model.updated_at)
                if then.tzinfo is None:
                    then = then.replace(tzinfo=timezone.utc)
                age_days = max(0.0, (self.clock() - then).total_seconds() / 86400.0)
                factor = math.pow(0.5, age_days / self.confidence_half_life_days)
                result["confidence"] = _clamp(model.confidence * factor)
                result["uncertainty"] = _clamp(1.0 - (1.0 - model.uncertainty) * factor)
            except (TypeError, ValueError):
                result["confidence"], result["uncertainty"] = 0.0, 1.0
        return result

    def observe(
        self,
        individual_id: str,
        event: str,
        *,
        intention: str | None = None,
        goal: str | None = None,
        belief: str | None = None,
        outcome: bool | None = None,
        note: str | None = None,
        evidence_kind: EvidenceKind = "inference",
        confidence: float = 1.0,
        source: str | None = None,
    ) -> dict[str, object]:
        """Revise a hypothesis from a conversation, act, promise, or outcome."""

        if evidence_kind not in _EVIDENCE_KINDS:
            raise ValueError(f"Unsupported evidence kind: {evidence_kind}")
        if outcome is not None and evidence_kind != "verified_outcome":
            # An alleged or inferred result remains a hypothesis.  Only a
            # verified outcome is allowed to revise the model as an outcome.
            outcome = None
        key = str(individual_id)
        model = self._models.get(key, MentalStateModel(key))
        event_key = str(event).lower()
        positive = event_key in {
            "conversation",
            "cooperation",
            "successful_cooperation",
            "promise_kept",
            "positive_outcome",
        }
        negative = event_key in {
            "conflict",
            "cooperation_failure",
            "promise_broken",
            "negative_outcome",
        }
        if outcome is not None:
            positive, negative = outcome, not outcome

        if goal and goal not in model.supposed_goals:
            model.supposed_goals.append(goal)
        if intention:
            previous = model.intentions.get(intention, 0.5)
            model.intentions[intention] = _clamp(
                previous + (0.25 if positive else -0.4 if negative else 0.08)
            )
        if belief:
            previous = model.attributed_beliefs.get(belief, 0.5)
            model.attributed_beliefs[belief] = _clamp(
                previous + (0.15 if not negative else -0.25)
            )
        if positive:
            model.reliability = _clamp(model.reliability + 0.1)
            model.reciprocity = min(1.0, model.reciprocity + 0.15)
        elif negative:
            model.reliability = _clamp(model.reliability - 0.18)
            model.reciprocity = max(-1.0, model.reciprocity - 0.2)
        kind_weight = {
            "verified_outcome": 1.0,
            "direct_observation": 0.75,
            "other_statement": 0.45,
            "inference": 0.25,
        }[evidence_kind]
        evidence_strength = (
            0.14 if outcome is not None or "promise" in event_key else 0.08
        )
        evidence_strength *= kind_weight * _clamp(confidence)
        model.confidence = _clamp(model.confidence + evidence_strength)
        model.uncertainty = _clamp(1.0 - model.confidence)
        model.version += 1
        model.updated_at = self.clock().isoformat()
        item: dict[str, object] = {
            "event": event,
            "at": model.updated_at,
            "evidence_kind": evidence_kind,
            "confidence": _clamp(confidence),
            "asserted_fact": evidence_kind == "verified_outcome",
        }
        for name, value in (
            ("intention", intention),
            ("goal", goal),
            ("belief", belief),
            ("outcome", outcome),
            ("note", note),
        ):
            if value is not None:
                item[name] = value
        if source is not None:
            item["source"] = source
        model.evidence = (model.evidence + [item])[-_EVIDENCE_LIMIT:]
        self._models[key] = model
        self._save()
        return self.get(key)


def _strings(value: object) -> list[str]:
    return (
        [item for item in value if isinstance(item, str)]
        if isinstance(value, list)
        else []
    )


def _scores(value: object) -> dict[str, float]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, float] = {}
    for key, score in value.items():
        if isinstance(key, str):
            try:
                result[key] = _clamp(float(score))
            except (TypeError, ValueError):
                pass
    return result


def _evidence(value: object) -> list[dict[str, object]]:
    return (
        [dict(item) for item in value if isinstance(item, dict)][-_EVIDENCE_LIMIT:]
        if isinstance(value, list)
        else []
    )
