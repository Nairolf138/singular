"""Aggregation service making :mod:`identity.self_model` the single source of truth."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .coherence import IdentityInvariants
from .self_model import SelfModelStore, _now


class IdentityCoreService:
    """Import legacy identity projections once and synchronize all consumers.

    ``root`` may be either a life directory (containing ``mem``) or its memory
    directory.  The core is always stored beside the other memory artifacts.
    """

    def __init__(self, root: Path | str) -> None:
        candidate = Path(root)
        self.mem = candidate if candidate.name == "mem" else candidate / "mem"
        self.mem.mkdir(parents=True, exist_ok=True)
        self.store = SelfModelStore(self.mem / "self_model.json")

    @staticmethod
    def _json(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _unique(*groups: Any) -> list[Any]:
        result: list[Any] = []
        for group in groups:
            if not isinstance(group, list):
                continue
            for value in group:
                if value not in result:
                    result.append(value)
        return result

    def synchronize(self, psyche: Any | None = None) -> dict[str, Any]:
        """Merge birth/narrative/psyche signals, then project the canonical core."""
        model = self.store.read()
        biography = self._json(self.mem / "biography.json")
        narrative = self._json(self.mem / "self_narrative.json")
        psyche_data = self._json(self.mem / "psyche.json")
        identity = biography.get("identity", {}) if isinstance(biography.get("identity"), Mapping) else {}
        narrative_identity = narrative.get("identity", {}) if isinstance(narrative.get("identity"), Mapping) else {}

        # Birth data is authoritative when a core still contains defaults.
        if model["name"] == "Singular":
            model["name"] = str(identity.get("name") or narrative_identity.get("name") or model["name"])
        if identity.get("id"):
            model["stable_id"] = str(identity["id"])
        summaries = biography.get("self_summaries", [])
        if not model["biographical_summary"] and isinstance(summaries, list):
            model["biographical_summary"] = " ".join(
                str(item.get("text", "")).strip() for item in summaries if isinstance(item, Mapping) and item.get("text")
            )
        certificate = biography.get("birth_certificate")
        if isinstance(certificate, Mapping) and not model["founding_events"]:
            model["founding_events"] = [dict(certificate)]

        commitments = psyche_data.get("identity_commitments", {})
        if psyche is not None:
            commitments = getattr(psyche, "identity_commitments", commitments)
        if not isinstance(commitments, Mapping):
            commitments = {}
        model["cardinal_values"] = self._unique(model["cardinal_values"], commitments.get("values"))
        model["red_lines"] = self._unique(model["red_lines"], commitments.get("red_lines"))
        # Older psyche state had no separate commitments list; values remain
        # values and are not silently promoted to promises.
        wounds = getattr(psyche, "identity_wounds", psyche_data.get("identity_wounds", 0.0))
        try:
            wound_score = float(wounds)
        except (TypeError, ValueError):
            wound_score = 0.0
        if wound_score > 0 and not model["identity_wounds"]:
            model["identity_wounds"].append({"kind": "legacy_psyche_wound", "severity": wound_score})

        # Psyche traits are observations, not ownership of identity.
        trait_source = psyche if psyche is not None else psyche_data
        for trait in ("curiosity", "patience", "playfulness", "optimism", "resilience"):
            value = getattr(trait_source, trait, None) if psyche is not None else trait_source.get(trait)
            if value is not None:
                self._merge_trait(model, trait, value)
        model["updated_at"] = _now()
        self.store.write(model)
        self._project(model, psyche)
        return model

    def _merge_trait(self, model: dict[str, Any], name: str, value: Any) -> None:
        now = _now()
        old = model["traits"].get(name, {})
        model["traits"][name] = {"value": str(value), "source": "psyche",
                                  "confidence": float(old.get("confidence", 1.0)),
                                  "observed_at": old.get("observed_at", now), "last_confirmed_at": now}

    def _project(self, model: dict[str, Any], psyche: Any | None) -> None:
        """Update compatibility projections without giving them ownership."""
        if psyche is not None:
            psyche.identity_commitments = {"values": list(model["cardinal_values"]),
                                           "red_lines": list(model["red_lines"])}
            psyche.identity_wounds = max(
                (float(w.get("severity", 0.0)) for w in model["identity_wounds"] if isinstance(w, Mapping)),
                default=0.0,
            )
        narrative_path = self.mem / "self_narrative.json"
        if narrative_path.exists():
            from ..self_narrative import load, save
            story = load(narrative_path)
            story.identity.name = model["name"]
            save(story, narrative_path)

    def coherence_invariants(self) -> IdentityInvariants:
        """Build the coherence guard input directly from the canonical core."""
        model = self.store.read()
        return IdentityInvariants(
            life_name=model["name"], cardinal_values=tuple(model["cardinal_values"]),
            long_term_commitments=tuple(model["commitments"]),
        )


# Less domain-specific alias for callers looking for an aggregation service.
IdentityAggregationService = IdentityCoreService
