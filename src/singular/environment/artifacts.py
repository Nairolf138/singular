"""Utilities to generate and persist simple artifacts."""
from __future__ import annotations

import os
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

_BASE_DIR = Path(os.environ.get("SINGULAR_HOME", "."))
ARTIFACTS_DIR = _BASE_DIR / "runs" / "artifacts"


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


def _save_metadata(path: Path, mood: str, resources: dict | None = None) -> Path:
    """Persist metadata for the artifact located at ``path``."""

    meta = {
        "date": datetime.utcnow().isoformat(timespec="seconds"),
        "mood": mood,
        "resources": resources or {},
    }
    meta_path = path.with_suffix(path.suffix + ".json")
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    return meta_path


def create_text_art(
    text: str,
    *,
    name: str = "text_art",
    mood: str = "neutre",
    resources: dict | None = None,
    directory: Path | None = None,
) -> Path:
    """Create a text artifact and save accompanying metadata."""

    directory = directory or ARTIFACTS_DIR
    path = save_text(name, text, directory)
    _save_metadata(path, mood, resources)
    return path


def create_ascii_drawing(
    width: int,
    height: int,
    char: str = "*",
    *,
    name: str = "drawing",
    mood: str = "neutre",
    resources: dict | None = None,
    directory: Path | None = None,
) -> Path:
    """Create a simple ASCII drawing and save accompanying metadata."""

    directory = directory or ARTIFACTS_DIR
    path = save_drawing(name, width, height, char, directory)
    _save_metadata(path, mood, resources)
    return path


def create_simple_melody(
    notes: Iterable[str],
    *,
    name: str = "melody",
    mood: str = "neutre",
    resources: dict | None = None,
    directory: Path | None = None,
) -> Path:
    """Create a simple melody and save accompanying metadata."""

    directory = directory or ARTIFACTS_DIR
    path = save_music(name, notes, directory)
    _save_metadata(path, mood, resources)
    return path
