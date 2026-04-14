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

from .governance.policy import MutationGovernancePolicy

_REGISTRY_DIRNAME = "lives"
_REGISTRY_FILENAME = "registry.json"
_RELATIONS_JOURNAL = "lives_relations.jsonl"

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class LifeMetadata:
    """Metadata describing a single life instance."""

    name: str
    slug: str
    path: Path
    created_at: str
    status: str = "active"
    parents: tuple[str, ...] = ()
    children: tuple[str, ...] = ()
    allies: tuple[str, ...] = ()
    rivals: tuple[str, ...] = ()
    proximity_score: float = 0.5
    lineage_depth: int = 0

    def to_payload(self) -> Dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return {
            "name": self.name,
            "slug": self.slug,
            "path": str(self.path),
            "created_at": self.created_at,
            "status": self.status,
            "parents": list(self.parents),
            "children": list(self.children),
            "allies": list(self.allies),
            "rivals": list(self.rivals),
            "proximity_score": self.proximity_score,
            "lineage_depth": self.lineage_depth,
        }

    @classmethod
    def from_payload(cls, data: Dict[str, Any]) -> "LifeMetadata":
        """Build metadata from a registry payload."""
        proximity_score = data.get("proximity_score", 0.5)
        if not isinstance(proximity_score, (int, float)):
            proximity_score = 0.5
        return cls(
            name=str(data["name"]),
            slug=str(data["slug"]),
            path=Path(data["path"]),
            created_at=str(data["created_at"]),
            status=str(data.get("status", "active")),
            parents=tuple(str(item) for item in data.get("parents", []) if isinstance(item, str)),
            children=tuple(str(item) for item in data.get("children", []) if isinstance(item, str)),
            allies=tuple(str(item) for item in data.get("allies", []) if isinstance(item, str)),
            rivals=tuple(str(item) for item in data.get("rivals", []) if isinstance(item, str)),
            proximity_score=max(0.0, min(1.0, float(proximity_score))),
            lineage_depth=max(0, int(data.get("lineage_depth", 0))),
        )


def _registry_path(root: Path | None = None) -> Path:
    root = root or get_registry_root()
    return root / _REGISTRY_DIRNAME / _REGISTRY_FILENAME


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _relations_journal_path() -> Path:
    return get_registry_root() / "mem" / _RELATIONS_JOURNAL


def _log_relations_event(event: str, *, actor: str, target: str | None = None, details: dict[str, Any] | None = None) -> None:
    journal = _relations_journal_path()
    journal.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": _now_iso(),
        "event": event,
        "actor": actor,
        "target": target,
        "details": details or {},
    }
    with journal.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _govern_relation_operation(op_name: str) -> None:
    policy = MutationGovernancePolicy()
    decision = policy.evaluate_skill_execution(skill_name=f"lives.{op_name}", capability="filesystem.write")
    policy.record_skill_execution(skill_name=f"lives.{op_name}", success=decision.allowed)
    if not decision.allowed:
        raise PermissionError(f"opération bloquée par la gouvernance: {decision.reason}")


def get_registry_root() -> Path:
    """Return the directory where the life registry is stored."""

    raw = os.environ.get("SINGULAR_ROOT")
    if raw:
        return Path(raw).expanduser()

    default_home = Path.home() / ".singular"
    cwd = Path.cwd()
    registry_path = cwd / _REGISTRY_DIRNAME / _REGISTRY_FILENAME

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
    normalized = status.strip().lower()
    if normalized not in {"active", "extinct"}:
        raise ValueError(f"unsupported life status '{status}'")
    registry = load_registry()
    lives: dict[str, LifeMetadata] = registry.get("lives", {})
    metadata = lives.get(slug)
    if metadata is None or metadata.status == normalized:
        return
    metadata.status = normalized
    save_registry(registry)


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "life"


def _resolve_life_metadata(name: str) -> tuple[dict[str, Any], str, LifeMetadata]:
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


def create_life(name: str, *, parents: tuple[str, ...] = ()) -> LifeMetadata:
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

    created_at = _now_iso()
    lineage_depth = 0
    valid_parents = tuple(parent for parent in parents if parent in lives)
    for parent_slug in valid_parents:
        parent_meta = lives.get(parent_slug)
        if parent_meta is not None:
            lineage_depth = max(lineage_depth, parent_meta.lineage_depth + 1)

    metadata = LifeMetadata(
        name=name,
        slug=slug,
        path=life_dir,
        created_at=created_at,
        status="active",
        parents=valid_parents,
        lineage_depth=lineage_depth,
    )

    lives[slug] = metadata
    for parent_slug in valid_parents:
        parent_meta = lives.get(parent_slug)
        if parent_meta is None:
            continue
        if slug not in parent_meta.children:
            parent_meta.children = tuple(parent_meta.children) + (slug,)

    registry["active"] = slug
    save_registry(registry)
    return metadata


def set_proximity(name: str, score: float) -> LifeMetadata:
    _govern_relation_operation("set_proximity")
    registry, slug, metadata = _resolve_life_metadata(name)
    metadata.proximity_score = max(0.0, min(1.0, float(score)))
    save_registry(registry)
    _log_relations_event("proximity.set", actor=slug, details={"proximity_score": metadata.proximity_score})
    return metadata


def list_relations(name: str | None = None) -> dict[str, Any]:
    registry = load_registry()
    lives: dict[str, LifeMetadata] = registry.get("lives", {})
    active = registry.get("active")
    focus_slug = active if name is None else None
    if name is not None:
        _, focus_slug, _ = _resolve_life_metadata(name)
    if focus_slug is None or focus_slug not in lives:
        raise KeyError(name or "active")
    focus = lives[focus_slug]

    family_nodes = []
    for slug in sorted(set(focus.parents) | {focus_slug} | set(focus.children)):
        meta = lives.get(slug)
        if meta is None:
            continue
        family_nodes.append({"slug": slug, "name": meta.name, "status": meta.status})

    social_nodes = []
    social_edges = []
    for slug, meta in sorted(lives.items()):
        social_nodes.append({"slug": slug, "name": meta.name, "proximity_score": meta.proximity_score})
        for ally in meta.allies:
            if ally in lives:
                social_edges.append({"source": slug, "target": ally, "kind": "ally"})
        for rival in meta.rivals:
            if rival in lives:
                social_edges.append({"source": slug, "target": rival, "kind": "rival"})

    active_conflicts = sorted({tuple(sorted((slug, rival))) for slug, meta in lives.items() for rival in meta.rivals if rival in lives})
    return {
        "active": active,
        "focus": {
            "slug": focus_slug,
            "name": focus.name,
            "parents": list(focus.parents),
            "children": list(focus.children),
            "allies": list(focus.allies),
            "rivals": list(focus.rivals),
            "proximity_score": focus.proximity_score,
        },
        "family": {"nodes": family_nodes},
        "social": {"nodes": social_nodes, "edges": social_edges},
        "active_conflicts": [{"life_a": a, "life_b": b} for a, b in active_conflicts],
    }


def _link_relation(actor: LifeMetadata, target_slug: str, *, relation: str) -> None:
    values = list(getattr(actor, relation))
    if target_slug not in values:
        values.append(target_slug)
        setattr(actor, relation, tuple(values))


def _unlink_relation(actor: LifeMetadata, target_slug: str, *, relation: str) -> None:
    values = [item for item in getattr(actor, relation) if item != target_slug]
    setattr(actor, relation, tuple(values))


def ally_lives(name: str, ally_name: str) -> tuple[LifeMetadata, LifeMetadata]:
    _govern_relation_operation("ally")
    registry, slug, meta = _resolve_life_metadata(name)
    lives: dict[str, LifeMetadata] = registry.setdefault("lives", {})
    _, ally_slug, ally_meta = _resolve_life_metadata(ally_name)
    if slug == ally_slug:
        raise ValueError("une vie ne peut pas devenir son propre allié")
    _link_relation(meta, ally_slug, relation="allies")
    _link_relation(ally_meta, slug, relation="allies")
    _unlink_relation(meta, ally_slug, relation="rivals")
    _unlink_relation(ally_meta, slug, relation="rivals")
    save_registry(registry)
    _log_relations_event("ally", actor=slug, target=ally_slug)
    return meta, ally_meta


def rival_lives(name: str, rival_name: str) -> tuple[LifeMetadata, LifeMetadata]:
    _govern_relation_operation("rival")
    registry, slug, meta = _resolve_life_metadata(name)
    lives: dict[str, LifeMetadata] = registry.setdefault("lives", {})
    _, rival_slug, rival_meta = _resolve_life_metadata(rival_name)
    if slug == rival_slug:
        raise ValueError("une vie ne peut pas devenir sa propre rivale")
    _link_relation(meta, rival_slug, relation="rivals")
    _link_relation(rival_meta, slug, relation="rivals")
    _unlink_relation(meta, rival_slug, relation="allies")
    _unlink_relation(rival_meta, slug, relation="allies")
    save_registry(registry)
    _log_relations_event("rival", actor=slug, target=rival_slug)
    return meta, rival_meta


def reconcile_lives(name: str, other_name: str) -> tuple[LifeMetadata, LifeMetadata]:
    _govern_relation_operation("reconcile")
    registry, slug, meta = _resolve_life_metadata(name)
    _, other_slug, other_meta = _resolve_life_metadata(other_name)
    _unlink_relation(meta, other_slug, relation="rivals")
    _unlink_relation(other_meta, slug, relation="rivals")
    save_registry(registry)
    _log_relations_event("reconcile", actor=slug, target=other_slug)
    return meta, other_meta


def resolve_life(name: str | None) -> Path | None:
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


def bootstrap_life(name: str, seed: int | None = None, *, psyche_overrides: dict[str, float] | None = None, starter_profile: str = "minimal", starter_skills: list[str] | None = None) -> LifeMetadata:
    metadata = create_life(name)
    from .organisms.birth import birth
    birth(seed=seed, home=metadata.path, psyche_overrides=psyche_overrides, starter_profile=starter_profile, starter_skills=starter_skills)
    registry = load_registry()
    lives: dict[str, LifeMetadata] = registry.get("lives", {})
    return lives.get(metadata.slug, metadata)


def delete_life(name: str) -> LifeMetadata:
    registry, slug, metadata = _resolve_life_metadata(name)
    lives: dict[str, LifeMetadata] = registry.setdefault("lives", {})
    try:
        shutil.rmtree(metadata.path)
    except FileNotFoundError:
        pass
    lives.pop(slug, None)
    for meta in lives.values():
        meta.parents = tuple(item for item in meta.parents if item != slug)
        meta.children = tuple(item for item in meta.children if item != slug)
        meta.allies = tuple(item for item in meta.allies if item != slug)
        meta.rivals = tuple(item for item in meta.rivals if item != slug)
    if registry.get("active") == slug:
        registry["active"] = next(iter(lives), None)
    save_registry(registry)
    return metadata


def archive_life(name: str) -> LifeMetadata:
    registry, slug, metadata = _resolve_life_metadata(name)
    metadata.status = "extinct"
    if registry.get("active") == slug:
        registry["active"] = next((key for key in registry["lives"] if key != slug), None)
    save_registry(registry)
    return metadata


def memorialize_life(name: str, *, message: str) -> Path:
    _, _, metadata = _resolve_life_metadata(name)
    memorial_dir = metadata.path / "mem"
    memorial_dir.mkdir(parents=True, exist_ok=True)
    memorial_file = memorial_dir / "memorial.json"
    payload = {"life": metadata.slug, "written_at": _now_iso(), "message": message.strip()}
    memorial_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return memorial_file


def clone_life(name: str, *, new_name: str | None = None) -> LifeMetadata:
    _, source_slug, source = _resolve_life_metadata(name)
    clone_name = new_name or f"{source.name} clone"
    clone_meta = create_life(clone_name, parents=(source_slug,))
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
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        return


def uninstall_singular(purge_lives: bool) -> None:
    root = get_registry_root()
    if not root.exists():
        return
    targets = ["lives", "mem", "runs"] if purge_lives else ["mem", "runs"]
    for target in targets:
        _remove_tree(root / target)
    if purge_lives:
        try:
            root.rmdir()
        except (FileNotFoundError, OSError):
            return
