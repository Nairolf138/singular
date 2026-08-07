"""Versioned, auditable contract for intentionally supplied demonstrations."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence


DEMONSTRATION_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class DemonstrationEvent:
    """A consent-bearing learning event; ordinary interactions are never examples."""

    observation: Sequence[Any]
    action: Sequence[Any]
    result: Sequence[Any] = ()
    demonstrator: str = "unknown"
    consent: Mapping[str, Any] = field(default_factory=lambda: {"granted": False})
    context: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)
    safety_constraints: Sequence[str] = ()
    skill: str = "imitated_skill"
    is_demonstration: bool = True
    schema_version: int = DEMONSTRATION_SCHEMA_VERSION
    created_at: float = field(default_factory=time.time)

    def validate(self) -> None:
        if self.schema_version != DEMONSTRATION_SCHEMA_VERSION:
            raise ValueError(f"unsupported demonstration schema: {self.schema_version}")
        if self.is_demonstration is not True:
            raise ValueError("an explicit is_demonstration=true indication is required")
        if self.consent.get("granted") is not True:
            raise ValueError("explicit demonstrator consent is required")
        if not self.demonstrator.strip() or self.demonstrator == "unknown":
            raise ValueError("demonstrator identity is required")
        if not self.provenance:
            raise ValueError("demonstration provenance is required")
        if not self.safety_constraints:
            raise ValueError("safety constraints are required")
        if not self.observation or len(self.observation) != len(self.action):
            raise ValueError("observation and action must be non-empty and aligned")
        if self.result and len(self.result) != len(self.action):
            raise ValueError("result and action must be aligned")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_interaction(
        cls, payload: Mapping[str, Any], *, source: str
    ) -> "DemonstrationEvent | None":
        """Return an event only when a human/agent explicitly labels the interaction."""

        if payload.get("is_demonstration") is not True:
            return None
        event = cls(
            observation=payload.get("observations", payload.get("observation", ())),
            action=payload.get("actions", payload.get("action", ())),
            result=payload.get("results", payload.get("result", ())),
            demonstrator=str(payload.get("demonstrator", "unknown")),
            consent=dict(payload.get("consent", {})),
            context=dict(payload.get("context", {})),
            provenance={"source": source, **dict(payload.get("provenance", {}))},
            safety_constraints=tuple(payload.get("safety_constraints", ())),
            skill=str(payload.get("name", payload.get("skill", "imitated_skill"))),
            is_demonstration=True,
            schema_version=int(
                payload.get("schema_version", DEMONSTRATION_SCHEMA_VERSION)
            ),
        )
        event.validate()
        return event
