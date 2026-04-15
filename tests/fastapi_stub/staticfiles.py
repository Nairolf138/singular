from __future__ import annotations

from pathlib import Path


class StaticFiles:
    """Minimal stub compatible with fastapi.staticfiles.StaticFiles."""

    def __init__(self, directory: str | Path, **_kwargs: object) -> None:
        self.directory = Path(directory)
