"""Memory management utilities.

JSON is used for most memory files.  The ``values.yaml`` file is only handled
when the optional :mod:`PyYAML <yaml>` package is available.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import os


def get_base_dir() -> Path:
    """Return the base directory for persistent files."""
    return Path(os.environ.get("SINGULAR_HOME", "."))


def get_mem_dir() -> Path:
    """Return the base memory directory."""
    return get_base_dir() / "mem"


def get_profile_file() -> Path:
    """Return the path to the profile JSON file."""
    return get_mem_dir() / "profile.json"


def get_values_file() -> Path:
    """Return the path to the values YAML file."""
    return get_mem_dir() / "values.yaml"


def get_episodic_file() -> Path:
    """Return the path to the episodic JSONL file."""
    return get_mem_dir() / "episodic.jsonl"


def get_skills_file() -> Path:
    """Return the path to the skills JSON file."""
    return get_mem_dir() / "skills.json"


def get_psyche_file() -> Path:
    """Return the path to the psyche JSON file."""
    return get_mem_dir() / "psyche.json"


def _ensure_dir(path: Path) -> None:
    """Ensure the parent directory of ``path`` exists."""
    path.parent.mkdir(parents=True, exist_ok=True)


def ensure_memory_structure(mem_dir: Path | str | None = None) -> None:
    """Create the memory directory structure if it does not exist."""
    if mem_dir is None:
        mem_dir = get_mem_dir()
    mem_dir = Path(mem_dir)
    mem_dir.mkdir(parents=True, exist_ok=True)
    (mem_dir / "profile.json").touch(exist_ok=True)
    (mem_dir / "values.yaml").touch(exist_ok=True)
    (mem_dir / "episodic.jsonl").touch(exist_ok=True)
    (mem_dir / "skills.json").touch(exist_ok=True)
    (mem_dir / "psyche.json").touch(exist_ok=True)


# ---------------------------------------------------------------------------
# Profile helpers
# ---------------------------------------------------------------------------


def read_profile(path: Path | str | None = None) -> dict[str, Any]:
    """Read the profile JSON file."""
    if path is None:
        path = get_profile_file()
    path = Path(path)
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as file:
        try:
            return json.load(file)
        except json.JSONDecodeError:
            return {}


def write_profile(profile: dict[str, Any], path: Path | str | None = None) -> None:
    """Write the profile JSON file."""
    if path is None:
        path = get_profile_file()
    path = Path(path)
    _ensure_dir(path)
    with path.open("w", encoding="utf-8") as file:
        json.dump(profile, file)


def update_trait(
    trait: str, value: Any, path: Path | str | None = None
) -> dict[str, Any]:
    """Update or add a trait in the profile file."""
    profile = read_profile(path)
    profile[trait] = value
    write_profile(profile, path)
    return profile


# ---------------------------------------------------------------------------
# Values helpers
# ---------------------------------------------------------------------------


def read_values(path: Path | str | None = None) -> dict[str, Any]:
    """Read the values YAML file.

    Returns an empty dict if :mod:`pyyaml` is not installed.
    """
    if path is None:
        path = get_values_file()
    path = Path(path)
    if not path.exists():
        return {}
    try:
        import yaml  # type: ignore
    except ImportError:
        # PyYAML is optional; return an empty mapping if it's missing
        return {}
    with path.open(encoding="utf-8") as file:
        data = yaml.safe_load(file)
    return data or {}


def write_values(values: dict[str, Any], path: Path | str | None = None) -> None:
    """Write the values YAML file.

    Requires :mod:`pyyaml` to be installed.
    """
    if path is None:
        path = get_values_file()
    path = Path(path)
    _ensure_dir(path)
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "PyYAML is required to write values. Please install PyYAML."
        ) from exc
    with path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(values, file)


# ---------------------------------------------------------------------------
# Episodic helpers
# ---------------------------------------------------------------------------


def read_episodes(path: Path | str | None = None) -> list[dict[str, Any]]:
    """Read all episodes from the JSONL file."""
    if path is None:
        path = get_episodic_file()
    path = Path(path)
    if not path.exists():
        return []
    episodes = []
    with path.open(encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            episodes.append(json.loads(line))
    return episodes


def add_episode(episode: dict[str, Any], path: Path | str | None = None) -> None:
    """Append a new episode to the episodic memory file."""
    if path is None:
        path = get_episodic_file()
    path = Path(path)
    _ensure_dir(path)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(episode) + "\n")


# ---------------------------------------------------------------------------
# Skills helpers
# ---------------------------------------------------------------------------


def read_skills(path: Path | str | None = None) -> dict[str, Any]:
    """Read the skills JSON file."""
    if path is None:
        path = get_skills_file()
    path = Path(path)
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as file:
        try:
            return json.load(file)
        except json.JSONDecodeError:
            return {}


def write_skills(skills: dict[str, Any], path: Path | str | None = None) -> None:
    """Write the skills JSON file."""
    if path is None:
        path = get_skills_file()
    path = Path(path)
    _ensure_dir(path)
    with path.open("w", encoding="utf-8") as file:
        json.dump(skills, file)


def update_score(
    skill: str, score: float, path: Path | str | None = None
) -> dict[str, Any]:
    """Update a skill score in the skills file."""
    skills = read_skills(path)
    skills[skill] = score
    write_skills(skills, path)
    return skills


# ---------------------------------------------------------------------------
# Psyche helpers
# ---------------------------------------------------------------------------


def read_psyche(path: Path | str | None = None) -> dict[str, Any]:
    """Read the psyche JSON file."""
    if path is None:
        path = get_psyche_file()
    path = Path(path)
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as file:
        try:
            return json.load(file)
        except json.JSONDecodeError:
            return {}


def write_psyche(state: dict[str, Any], path: Path | str | None = None) -> None:
    """Write the psyche JSON file."""
    if path is None:
        path = get_psyche_file()
    path = Path(path)
    _ensure_dir(path)
    with path.open("w", encoding="utf-8") as file:
        json.dump(state, file)
