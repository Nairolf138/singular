"""Identity file creation and reading utilities."""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class Identity:
    """Data class representing an identity."""

    name: str
    soulseed: str
    id: str
    born_at: str


def create_identity(name: str, soulseed: str, path: Path | str = Path("id.json")) -> Identity:
    """Create an identity JSON file.

    Parameters
    ----------
    name:
        Name of the identity.
    soulseed:
        Seed string representing the soul.
    path:
        Path where the ``id.json`` file will be written.

    Returns
    -------
    Identity
        The identity information that was written to the file.
    """

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
    """Read an identity JSON file.

    Parameters
    ----------
    path:
        Path to the ``id.json`` file.

    Returns
    -------
    Identity
        The identity information loaded from the file.
    """

    path = Path(path)
    with path.open(encoding="utf-8") as file:
        data: dict[str, Any] = json.load(file)

    return Identity(**data)
