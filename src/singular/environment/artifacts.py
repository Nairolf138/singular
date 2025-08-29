"""Utilities to generate and persist simple artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

ARTIFACTS_DIR = Path("./artifacts")


def _ensure_dir(directory: Path | None = None) -> Path:
    directory = directory or ARTIFACTS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def save_text(name: str, content: str, directory: Path | None = None) -> Path:
    """Save *content* as a text artifact named *name*.

    Returns the path to the created file.
    """

    directory = _ensure_dir(directory)
    path = directory / f"{name}.txt"
    path.write_text(content, encoding="utf-8")
    return path


def save_drawing(
    name: str,
    width: int,
    height: int,
    char: str = "*",
    directory: Path | None = None,
) -> Path:
    """Generate a simple ASCII drawing and persist it as a text file."""

    lines = [char * width for _ in range(height)]
    content = "\n".join(lines)
    return save_text(name, content, directory)


def save_music(name: str, notes: Iterable[str], directory: Path | None = None) -> Path:
    """Store a sequence of *notes* as a rudimentary music artifact."""

    directory = _ensure_dir(directory)
    path = directory / f"{name}.abc"
    path.write_text(" ".join(notes), encoding="utf-8")
    return path
