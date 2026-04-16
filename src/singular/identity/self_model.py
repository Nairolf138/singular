"""Stable self-model storage preserving identity invariants."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from ..io_utils import atomic_write_text


class IdentityInvariantError(ValueError):
    """Raised when a retention/compaction request violates identity invariants."""


class SelfModelStore:
    """Persistent self-model for traits, preferences, and constraints."""

    _REQUIRED_ROOT_KEYS = {"traits", "preferences", "constraints"}

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.write(self._default_model())

    def _default_model(self) -> dict[str, Any]:
        return {
            "traits": {},
            "preferences": {},
            "constraints": {},
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    def read(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = self._default_model()
        if not isinstance(payload, dict):
            payload = self._default_model()
        for key in self._REQUIRED_ROOT_KEYS:
            if not isinstance(payload.get(key), dict):
                payload[key] = {}
        payload.setdefault("updated_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        return payload

    def write(self, model: dict[str, Any]) -> None:
        missing = self._REQUIRED_ROOT_KEYS.difference(model)
        if missing:
            raise IdentityInvariantError(f"Missing invariant sections in self model: {sorted(missing)}")
        atomic_write_text(self.path, json.dumps(model, ensure_ascii=False, indent=2) + "\n")

    def apply_facts(self, facts: list[dict[str, Any]]) -> dict[str, Any]:
        model = self.read()
        for fact in facts:
            kind = str(fact.get("kind", ""))
            value = str(fact.get("value", "")).strip()
            confidence = float(fact.get("confidence", 0.5) or 0.5)
            if not value:
                continue
            if kind == "user_fact":
                model["traits"][value] = confidence
            elif kind == "preference":
                model["preferences"][value] = confidence
            elif kind == "constraint":
                model["constraints"][value] = confidence
        model["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.write(model)
        return model

    def compact(self, keep_top_n_per_section: int = 50) -> dict[str, Any]:
        """Compact model while keeping invariant root sections."""

        model = self.read()
        keep_n = max(1, keep_top_n_per_section)
        for section in self._REQUIRED_ROOT_KEYS:
            values = model.get(section, {})
            if not isinstance(values, dict):
                model[section] = {}
                continue
            top_items = sorted(values.items(), key=lambda item: float(item[1]), reverse=True)[:keep_n]
            model[section] = dict(top_items)
        model["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.write(model)
        return model
