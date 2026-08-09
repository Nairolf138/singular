"""Versioned, authoritative storage for the persistent identity core."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from ..io_utils import atomic_write_text

SCHEMA_VERSION = 3
METACOGNITION_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class IdentityInvariantError(ValueError):
    """Raised when a retention/compaction request violates identity invariants."""


class SelfModelStore:
    """Persistent identity core.

    Version 2 deliberately keeps autobiographical facts apart from personality
    traits.  Evidence-bearing sections contain records rather than bare scores,
    so their provenance survives restarts and consolidation.
    """

    _EVIDENCE_SECTIONS = (
        "autobiographical_facts",
        "traits",
        "preferences",
        "constraints",
    )
    _REQUIRED_ROOT_KEYS = set(_EVIDENCE_SECTIONS)

    @staticmethod
    def _default_metacognition() -> dict[str, Any]:
        return {
            "version": METACOGNITION_VERSION,
            "domains": {},
            "recurring_errors": {},
            "observed_biases": {},
            "effective_strategies": {},
            "failure_conditions": {},
            "calibration_history": [],
            "processed_evidence_refs": [],
            "updated_at": None,
        }

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.write(self._default_model())
        else:
            # Reading is also the on-disk migration boundary.
            model, migrated = self._read_and_migrate()
            if migrated:
                self.write(model)

    def _default_model(self) -> dict[str, Any]:
        now = _now()
        return {
            "schema_version": SCHEMA_VERSION,
            "stable_id": str(uuid4()),
            "name": "Singular",
            "biographical_summary": "",
            "founding_events": [],
            "autobiographical_facts": {},
            "traits": {},
            "preferences": {},
            "cardinal_values": [],
            "commitments": [],
            "red_lines": [],
            "identity_wounds": [],
            "constraints": {},
            "metacognition": self._default_metacognition(),
            "created_at": now,
            "updated_at": now,
        }

    @staticmethod
    def _record(value: str, raw: Any, now: str) -> dict[str, Any]:
        if isinstance(raw, Mapping):
            observed = str(raw.get("observed_at") or raw.get("observation_date") or now)
            return {
                "value": str(raw.get("value", value)),
                "source": str(raw.get("source") or "legacy:self_model"),
                "confidence": float(raw.get("confidence", 0.5) or 0.5),
                "observed_at": observed,
                "last_confirmed_at": str(raw.get("last_confirmed_at") or observed),
            }
        try:
            confidence = float(raw)
        except (TypeError, ValueError):
            confidence = 0.5
        return {
            "value": value,
            "source": "legacy:self_model",
            "confidence": confidence,
            "observed_at": now,
            "last_confirmed_at": now,
        }

    def _read_and_migrate(self) -> tuple[dict[str, Any], bool]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self._default_model(), True
        if not isinstance(raw, dict):
            return self._default_model(), True
        migrated = raw.get("schema_version") != SCHEMA_VERSION
        defaults = self._default_model()
        model = dict(raw)
        for key, value in defaults.items():
            if key not in model:
                model[key] = value
                migrated = True
        now = str(model.get("updated_at") or _now())
        for section in self._EVIDENCE_SECTIONS:
            values = model.get(section)
            if not isinstance(values, dict):
                model[section] = {}
                migrated = True
                continue
            normalized = {
                str(key): self._record(str(key), value, now)
                for key, value in values.items()
            }
            if normalized != values:
                model[section] = normalized
                migrated = True
        for section in (
            "founding_events",
            "cardinal_values",
            "commitments",
            "red_lines",
            "identity_wounds",
        ):
            if not isinstance(model.get(section), list):
                model[section] = []
                migrated = True
        metacognition = model.get("metacognition")
        if not isinstance(metacognition, dict):
            metacognition = self._default_metacognition()
            model["metacognition"] = metacognition
            migrated = True
        for key, value in self._default_metacognition().items():
            if key not in metacognition:
                metacognition[key] = value
                migrated = True
        metacognition["version"] = METACOGNITION_VERSION
        model["schema_version"] = SCHEMA_VERSION
        return model, migrated

    def read(self) -> dict[str, Any]:
        model, migrated = self._read_and_migrate()
        if migrated:
            self.write(model)
        return model

    def write(self, model: dict[str, Any]) -> None:
        missing = self._REQUIRED_ROOT_KEYS.difference(model)
        if missing:
            raise IdentityInvariantError(
                f"Missing invariant sections in self model: {sorted(missing)}"
            )
        model["schema_version"] = SCHEMA_VERSION
        atomic_write_text(
            self.path, json.dumps(model, ensure_ascii=False, indent=2) + "\n"
        )

    def apply_facts(self, facts: list[dict[str, Any]]) -> dict[str, Any]:
        """Merge extracted evidence without confusing biography and character."""
        model = self.read()
        now = _now()
        section_for_kind = {
            "user_fact": "autobiographical_facts",
            "autobiographical_fact": "autobiographical_facts",
            "trait": "traits",
            "preference": "preferences",
            "constraint": "constraints",
        }
        for fact in facts:
            section = section_for_kind.get(str(fact.get("kind", "")))
            value = str(fact.get("value", "")).strip()
            if not section or not value:
                continue
            previous = model[section].get(value, {})
            observed = str(
                fact.get("observed_at") or fact.get("observation_date") or now
            )
            model[section][value] = {
                "value": value,
                "source": str(
                    fact.get("source") or previous.get("source") or "unknown"
                ),
                "confidence": float(
                    fact.get("confidence", previous.get("confidence", 0.5)) or 0.5
                ),
                "observed_at": str(previous.get("observed_at") or observed),
                "last_confirmed_at": str(fact.get("last_confirmed_at") or observed),
            }
        model["updated_at"] = now
        self.write(model)
        return model

    def compact(self, keep_top_n_per_section: int = 50) -> dict[str, Any]:
        """Compact evidence only; never discard the durable identity fields."""
        model = self.read()
        keep_n = max(1, keep_top_n_per_section)
        for section in self._EVIDENCE_SECTIONS:
            values = model[section]
            model[section] = dict(
                sorted(
                    values.items(),
                    key=lambda item: float(item[1].get("confidence", 0.0)),
                    reverse=True,
                )[:keep_n]
            )
        model["updated_at"] = _now()
        self.write(model)
        return model
