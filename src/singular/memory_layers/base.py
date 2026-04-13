from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class MemoryRecord:
    """Generic memory record stored by backends."""

    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0


class MemoryBackend(Protocol):
    """Storage/search contract for memory layers."""

    def put(self, layer: str, record: MemoryRecord) -> None:
        """Persist a memory record in *layer*."""

    def search(self, layer: str, query: str, limit: int = 5) -> list[MemoryRecord]:
        """Return top matching records for *query*."""

    def delete(self, layer: str, record_id: str) -> bool:
        """Delete one record by id and return whether it existed."""
