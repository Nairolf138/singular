"""Deterministic social graph between pairs of lives."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import json

from singular.memory import _atomic_write_text, get_mem_dir
from singular.social.theory_of_mind import TheoryOfMindStore

_HISTORY_LIMIT = 20

_EVENT_DELTAS: dict[str, dict[str, float]] = {
    "entraide_reussie": {"affinity": 0.08, "trust": 0.12, "rivalry": -0.05},
    "successful_assistance": {"affinity": 0.08, "trust": 0.12, "rivalry": -0.05},
    "conflit_ressources": {"affinity": -0.06, "trust": -0.03, "rivalry": 0.1},
    "resource_conflict": {"affinity": -0.06, "trust": -0.03, "rivalry": 0.1},
    "echec_cooperation": {"affinity": -0.05, "trust": -0.1, "rivalry": 0.06},
    "cooperation_failure": {"affinity": -0.05, "trust": -0.1, "rivalry": 0.06},
    "sabotage_refuse": {"affinity": 0.05, "trust": 0.09, "rivalry": -0.08},
    "sabotage_refused": {"affinity": 0.05, "trust": 0.09, "rivalry": -0.08},
}


@dataclass(slots=True)
class PairRelation:
    affinity: float = 0.5
    trust: float = 0.5
    rivalry: float = 0.0
    history: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class SocialGraph:
    """Relationship model persisted as a pair-indexed graph."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (get_mem_dir() / "social_graph.json")
        self.theory_of_mind = TheoryOfMindStore(
            self.path.with_name("theory_of_mind.json")
        )
        self._relations: dict[str, PairRelation] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._relations = {}
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._relations = {}
            return
        relations = raw.get("relations") if isinstance(raw, dict) else None
        if not isinstance(relations, dict):
            self._relations = {}
            return
        parsed: dict[str, PairRelation] = {}
        for pair_key, payload in relations.items():
            if not isinstance(pair_key, str) or not isinstance(payload, dict):
                continue
            parsed[pair_key] = PairRelation(
                affinity=_clamp01(float(payload.get("affinity", 0.5))),
                trust=_clamp01(float(payload.get("trust", 0.5))),
                rivalry=_clamp01(float(payload.get("rivalry", 0.0))),
                history=_normalize_history(payload.get("history")),
            )
        self._relations = parsed

    def _save(self) -> None:
        payload = {
            "relations": {
                pair_key: relation.to_dict()
                for pair_key, relation in sorted(self._relations.items())
            }
        }
        _atomic_write_text(
            self.path,
            json.dumps(payload, ensure_ascii=False, indent=2),
        )

    @staticmethod
    def _pair_key(a: str, b: str) -> str:
        left, right = sorted((str(a), str(b)))
        return f"{left}::{right}"

    def get_relation(self, a: str, b: str) -> dict[str, object]:
        pair_key = self._pair_key(a, b)
        relation = self._relations.get(pair_key, PairRelation())
        return relation.to_dict()

    def update_relation(self, a: str, b: str, event: str) -> dict[str, object]:
        pair_key = self._pair_key(a, b)
        relation = self._relations.get(pair_key, PairRelation())
        deltas = _EVENT_DELTAS.get(event)
        if deltas is None:
            raise ValueError(
                f"Unsupported social event '{event}'. "
                f"Supported values: {', '.join(sorted(_EVENT_DELTAS))}"
            )

        relation.affinity = _clamp01(relation.affinity + deltas["affinity"])
        relation.trust = _clamp01(relation.trust + deltas["trust"])
        relation.rivalry = _clamp01(relation.rivalry + deltas["rivalry"])
        relation.history.append(
            {
                "event": event,
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )
        relation.history = relation.history[-_HISTORY_LIMIT:]
        self._relations[pair_key] = relation
        self._save()
        return relation.to_dict()

    def observe_mental_state(
        self, individual_id: str, event: str, **details: object
    ) -> dict[str, object]:
        """Update a peer hypothesis without changing the affective relation."""

        return self.theory_of_mind.observe(individual_id, event, **details)  # type: ignore[arg-type]

    def get_mental_state(self, individual_id: str) -> dict[str, object]:
        return self.theory_of_mind.get(individual_id)

    def record_interaction(
        self,
        observer: str,
        individual_id: str,
        event: str,
        **details: object,
    ) -> dict[str, object]:
        """Record evidence from an interaction and, when applicable, its relation.

        ``observer`` identifies whose point of view produced the hypothesis.  A
        graph instance belongs to one life, so only the observed individual's
        mental model is indexed; the affective pair remains independently
        indexed by both participants.
        """

        mental = self.observe_mental_state(individual_id, event, **details)
        relation_event = {
            "cooperation": "successful_assistance",
            "successful_cooperation": "successful_assistance",
            "conflict": "resource_conflict",
            "cooperation_failure": "cooperation_failure",
        }.get(event.lower())
        relation = (
            self.update_relation(observer, individual_id, relation_event)
            if relation_event is not None
            else self.get_relation(observer, individual_id)
        )
        return {"mental_state": mental, "relation": relation}


def _normalize_history(raw: object) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    history: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        event = item.get("event")
        at = item.get("at")
        if isinstance(event, str) and isinstance(at, str):
            history.append({"event": event, "at": at})
    return history[-_HISTORY_LIMIT:]


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def get_relation(a: str, b: str) -> dict[str, object]:
    """Return the relation state for a pair of lives."""

    return SocialGraph().get_relation(a, b)


def update_relation(a: str, b: str, event: str) -> dict[str, object]:
    """Apply a deterministic social update and persist graph state."""

    return SocialGraph().update_relation(a, b, event)
