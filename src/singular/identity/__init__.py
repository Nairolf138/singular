"""Identity primitives and memory consolidation helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .consolidation import ConsolidationPipeline, ConsolidationPolicy, ConsolidationResult
from .episodic_store import EpisodicStore
from .self_model import IdentityInvariantError, SelfModelStore
from .semantic_memory import SemanticMemoryStore


@dataclass
class Identity:
    """Data class representing an identity."""

    name: str
    soulseed: str
    id: str
    born_at: str


def create_identity(
    name: str, soulseed: str, path: Path | str = Path("id.json")
) -> Identity:
    """Create an identity JSON file."""

    identity = Identity(
        name=name,
        soulseed=soulseed,
        id=hashlib.sha256(f"{name}:{soulseed}".encode("utf-8")).hexdigest(),
        born_at=datetime.now(timezone.utc).isoformat(),
    )

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(identity.__dict__, file)

    return identity


def read_identity(path: Path | str = Path("id.json")) -> Identity:
    """Read an identity JSON file."""

    path = Path(path)
    with path.open(encoding="utf-8") as file:
        data: dict[str, Any] = json.load(file)

    return Identity(**data)


__all__ = [
    "ConsolidationPipeline",
    "ConsolidationPolicy",
    "ConsolidationResult",
    "EpisodicStore",
    "Identity",
    "IdentityInvariantError",
    "SemanticMemoryStore",
    "SelfModelStore",
    "create_identity",
    "read_identity",
]
