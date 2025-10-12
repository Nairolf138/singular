"""Utilities for managing multiple lives."""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

_REGISTRY_DIRNAME = "lives"
_REGISTRY_FILENAME = "registry.json"


@dataclass(slots=True)
class LifeMetadata:
    """Metadata describing a single life instance."""

    name: str
    slug: str
    path: Path
    created_at: str

    def to_payload(self) -> Dict[str, str]:
        """Return a JSON-serialisable representation."""
        return {
            "name": self.name,
            "slug": self.slug,
            "path": str(self.path),
            "created_at": self.created_at,
        }

    @classmethod
    def from_payload(cls, data: Dict[str, Any]) -> "LifeMetadata":
        """Build metadata from a registry payload."""
        return cls(
            name=str(data["name"]),
            slug=str(data["slug"]),
            path=Path(data["path"]),
            created_at=str(data["created_at"]),
        )


def _registry_path(root: Path | None = None) -> Path:
    root = root or get_registry_root()
    return root / _REGISTRY_DIRNAME / _REGISTRY_FILENAME


def get_registry_root() -> Path:
    """Return the directory where the life registry is stored."""

    raw = os.environ.get("SINGULAR_ROOT")
    if raw:
        root = Path(raw).expanduser()
    else:
        cwd = Path.cwd()
        default_home = Path.home() / ".singular"
        # Prefer the current working directory when it already contains
        # Singular artefacts. Otherwise fall back to ``~/.singular``.
        if (cwd / _REGISTRY_DIRNAME).exists() or (cwd / "mem").exists():
            root = cwd
        else:
            root = default_home
    return root


def load_registry() -> dict[str, Any]:
    """Load the life registry from disk."""

    path = _registry_path()
    if not path.exists():
        return {"active": None, "lives": {}}

    with path.open(encoding="utf-8") as fh:
        payload = json.load(fh)

    lives_payload = payload.get("lives", {})
    lives: dict[str, LifeMetadata] = {}
    for slug, data in lives_payload.items():
        try:
            lives[slug] = LifeMetadata.from_payload(data)
        except KeyError:
            continue

    active = payload.get("active")
    if active not in lives:
        active = None

    return {"active": active, "lives": lives}


def save_registry(registry: dict[str, Any]) -> None:
    """Persist the life registry to disk."""

    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    lives_payload: dict[str, Dict[str, str]] = {}
    for slug, meta in registry.get("lives", {}).items():
        if isinstance(meta, LifeMetadata):
            lives_payload[slug] = meta.to_payload()
        else:
            lives_payload[slug] = LifeMetadata.from_payload(meta).to_payload()

    payload = {
        "active": registry.get("active"),
        "lives": lives_payload,
    }

    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "life"


def create_life(name: str) -> LifeMetadata:
    """Create a new life directory and register it."""

    registry = load_registry()
    lives: dict[str, LifeMetadata] = registry.setdefault("lives", {})

    base_slug = _slugify(name)
    slug = base_slug
    counter = 1
    while slug in lives:
        counter += 1
        slug = f"{base_slug}-{counter}"

    root = get_registry_root()
    life_dir = root / _REGISTRY_DIRNAME / slug
    life_dir.mkdir(parents=True, exist_ok=True)

    created_at = datetime.now(timezone.utc).isoformat()
    metadata = LifeMetadata(name=name, slug=slug, path=life_dir, created_at=created_at)

    lives[slug] = metadata
    registry["active"] = slug
    save_registry(registry)

    return metadata


def resolve_life(name: str | None) -> Path | None:
    """Return the directory for the requested or active life."""

    registry = load_registry()
    lives: dict[str, LifeMetadata] = registry.get("lives", {})
    if not lives:
        return None

    target: LifeMetadata | None = None
    if name is None:
        active = registry.get("active")
        if isinstance(active, str):
            target = lives.get(active)
    else:
        if name in lives:
            target = lives[name]
        else:
            slug = _slugify(name)
            target = lives.get(slug)
            if target is None:
                for meta in lives.values():
                    if meta.name == name:
                        target = meta
                        break

    if target is None:
        return None

    if registry.get("active") != target.slug:
        registry["active"] = target.slug
        save_registry(registry)

    return target.path


def bootstrap_life(name: str, seed: int | None = None) -> LifeMetadata:
    """Create and initialise a life."""

    metadata = create_life(name)

    from .organisms.birth import birth  # Imported lazily to avoid cycles.

    birth(seed=seed, home=metadata.path)
    registry = load_registry()
    lives: dict[str, LifeMetadata] = registry.get("lives", {})
    return lives.get(metadata.slug, metadata)


def delete_life(name: str) -> LifeMetadata:
    """Remove a life from the registry and delete its directory."""

    registry = load_registry()
    lives: dict[str, LifeMetadata] = registry.setdefault("lives", {})
    if not lives:
        raise KeyError(name)

    slug: str | None = None
    metadata: LifeMetadata | None = None
    if name in lives:
        slug = name
        metadata = lives[name]
    else:
        candidate = _slugify(name)
        if candidate in lives:
            slug = candidate
            metadata = lives[candidate]
        else:
            for candidate_slug, meta in lives.items():
                if meta.name == name:
                    slug = candidate_slug
                    metadata = meta
                    break

    if slug is None or metadata is None:
        raise KeyError(name)

    try:
        shutil.rmtree(metadata.path)
    except FileNotFoundError:
        pass

    lives.pop(slug, None)
    if registry.get("active") == slug:
        registry["active"] = next(iter(lives), None)
    save_registry(registry)

    return metadata
