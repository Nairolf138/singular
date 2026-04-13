"""Utilities for managing multiple lives."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

_REGISTRY_DIRNAME = "lives"
_REGISTRY_FILENAME = "registry.json"

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class LifeMetadata:
    """Metadata describing a single life instance."""

    name: str
    slug: str
    path: Path
    created_at: str
    status: str = "active"

    def to_payload(self) -> Dict[str, str]:
        """Return a JSON-serialisable representation."""
        return {
            "name": self.name,
            "slug": self.slug,
            "path": str(self.path),
            "created_at": self.created_at,
            "status": self.status,
        }

    @classmethod
    def from_payload(cls, data: Dict[str, Any]) -> "LifeMetadata":
        """Build metadata from a registry payload."""
        return cls(
            name=str(data["name"]),
            slug=str(data["slug"]),
            path=Path(data["path"]),
            created_at=str(data["created_at"]),
            status=str(data.get("status", "active")),
        )


def _registry_path(root: Path | None = None) -> Path:
    root = root or get_registry_root()
    return root / _REGISTRY_DIRNAME / _REGISTRY_FILENAME


def get_registry_root() -> Path:
    """Return the directory where the life registry is stored."""

    raw = os.environ.get("SINGULAR_ROOT")
    if raw:
        return Path(raw).expanduser()

    default_home = Path.home() / ".singular"
    cwd = Path.cwd()
    registry_path = cwd / _REGISTRY_DIRNAME / _REGISTRY_FILENAME

    # CWD fallback is allowed only when an explicit, valid registry marker
    # exists. This avoids accidental detection based on unrelated directories
    # such as a plain ``mem/`` folder.
    if registry_path.exists():
        try:
            payload = json.loads(registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default_home
        if isinstance(payload, dict) and isinstance(payload.get("lives"), dict):
            return cwd

    return default_home


def load_registry() -> dict[str, Any]:
    """Load the life registry from disk."""

    path = _registry_path()
    default_registry = {"active": None, "lives": {}}

    try:
        with path.open(encoding="utf-8") as fh:
            payload = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        _LOGGER.warning("Failed to load life registry from %s: %s", path, exc)
        return default_registry

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


def set_life_status(slug: str, status: str) -> None:
    """Update a life status in the registry."""

    normalized = status.strip().lower()
    if normalized not in {"active", "extinct"}:
        raise ValueError(f"unsupported life status '{status}'")

    registry = load_registry()
    lives: dict[str, LifeMetadata] = registry.get("lives", {})
    metadata = lives.get(slug)
    if metadata is None:
        return
    if metadata.status == normalized:
        return

    metadata.status = normalized
    save_registry(registry)


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "life"


def _resolve_life_metadata(name: str) -> tuple[dict[str, Any], str, LifeMetadata]:
    """Resolve a life by slug or name and return ``(registry, slug, metadata)``."""

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
    return registry, slug, metadata


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
    metadata = LifeMetadata(
        name=name,
        slug=slug,
        path=life_dir,
        created_at=created_at,
        status="active",
    )

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

    registry, slug, metadata = _resolve_life_metadata(name)
    lives: dict[str, LifeMetadata] = registry.setdefault("lives", {})

    try:
        shutil.rmtree(metadata.path)
    except FileNotFoundError:
        pass

    lives.pop(slug, None)
    if registry.get("active") == slug:
        registry["active"] = next(iter(lives), None)
    save_registry(registry)

    return metadata


def archive_life(name: str) -> LifeMetadata:
    """Mark a life as extinct and return its metadata."""

    registry, slug, metadata = _resolve_life_metadata(name)
    metadata.status = "extinct"
    if registry.get("active") == slug:
        registry["active"] = next((key for key in registry["lives"] if key != slug), None)
    save_registry(registry)
    return metadata


def memorialize_life(name: str, *, message: str) -> Path:
    """Write a memorial note for a life and return the created file path."""

    _, _, metadata = _resolve_life_metadata(name)
    memorial_dir = metadata.path / "mem"
    memorial_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat()
    memorial_file = memorial_dir / "memorial.json"
    payload = {"life": metadata.slug, "written_at": stamp, "message": message.strip()}
    memorial_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return memorial_file


def clone_life(name: str, *, new_name: str | None = None) -> LifeMetadata:
    """Clone an existing life to a fresh life entry."""

    _, _, source = _resolve_life_metadata(name)
    clone_name = new_name or f"{source.name} clone"
    clone_meta = create_life(clone_name)
    shutil.copytree(source.path, clone_meta.path, dirs_exist_ok=True)
    registry = load_registry()
    lives: dict[str, LifeMetadata] = registry.get("lives", {})
    current = lives.get(clone_meta.slug)
    if current is not None:
        current.status = "active"
    registry["active"] = clone_meta.slug
    save_registry(registry)
    return lives.get(clone_meta.slug, clone_meta)


def _remove_tree(path: Path) -> None:
    """Remove a directory tree if it exists."""

    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        return


def uninstall_singular(purge_lives: bool) -> None:
    """Uninstall Singular data from ``SINGULAR_ROOT``.

    Cleanup targets are intentionally explicit:

    - ``--keep-lives`` mode removes only legacy/global technical artefacts
      at the root level: ``mem/`` and ``runs/``.
    - ``--purge-lives`` mode removes all Singular data trees under the root:
      ``lives/``, ``mem/`` and ``runs/``.
    """

    root = get_registry_root()
    if not root.exists():
        return

    targets = ["lives", "mem", "runs"] if purge_lives else ["mem", "runs"]
    for target in targets:
        _remove_tree(root / target)

    if purge_lives:
        try:
            root.rmdir()
        except FileNotFoundError:
            return
        except OSError:
            # Root is kept when not empty (e.g. user-managed files).
            return
