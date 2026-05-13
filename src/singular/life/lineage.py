"""Lineage records for organisms and generated mutations.

The public helpers in this module keep parent/child relationships explicit and
serialisable.  They are deliberately independent from the heavier ``lives``
registry so tests, tools, and future organism packages can record ancestry,
generation, mutation provenance, and score using the same compact schema.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class LineageRecord:
    """One organism or mutation node in a lineage graph."""

    organism_id: str
    parents: tuple[str, ...] = ()
    children: tuple[str, ...] = ()
    generation: int = 0
    mutation_source: str | None = None
    score: float | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serialisable representation."""

        payload = asdict(self)
        payload["parents"] = list(self.parents)
        payload["children"] = list(self.children)
        return payload


LineageRegistry = dict[str, LineageRecord]


def _unique(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        item = str(value).strip()
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return tuple(ordered)


def create_lineage_record(
    organism_id: str,
    *,
    parents: tuple[str, ...] | list[str] = (),
    children: tuple[str, ...] | list[str] = (),
    generation: int | None = None,
    mutation_source: str | None = None,
    score: float | None = None,
    metadata: Mapping[str, object] | None = None,
) -> LineageRecord:
    """Create a normalized lineage record.

    When ``generation`` is omitted, parentless records start at generation 0 and
    child records default to one generation after their parents.  A standalone
    record with parent identifiers but no registry therefore gets generation 1.
    """

    normalized_id = organism_id.strip()
    if not normalized_id:
        raise ValueError("organism_id must not be empty")
    normalized_parents = _unique(list(parents))
    normalized_children = _unique(list(children))
    resolved_generation = generation
    if resolved_generation is None:
        resolved_generation = 1 if normalized_parents else 0
    return LineageRecord(
        organism_id=normalized_id,
        parents=normalized_parents,
        children=normalized_children,
        generation=max(0, int(resolved_generation)),
        mutation_source=mutation_source,
        score=None if score is None else float(score),
        metadata=dict(metadata or {}),
    )


def register_lineage(
    registry: LineageRegistry,
    organism_id: str,
    *,
    parents: tuple[str, ...] | list[str] = (),
    generation: int | None = None,
    mutation_source: str | None = None,
    score: float | None = None,
    metadata: Mapping[str, object] | None = None,
) -> LineageRecord:
    """Register an organism and link it to its parents and children."""

    parent_ids = _unique(list(parents))
    if generation is None and parent_ids:
        generation = (
            max(
                (
                    registry[parent].generation
                    for parent in parent_ids
                    if parent in registry
                ),
                default=0,
            )
            + 1
        )
    existing = registry.get(organism_id)
    children = existing.children if existing else ()
    record = create_lineage_record(
        organism_id,
        parents=parent_ids,
        children=children,
        generation=generation,
        mutation_source=mutation_source,
        score=score,
        metadata=metadata,
    )
    registry[record.organism_id] = record

    for parent_id in parent_ids:
        parent = registry.get(parent_id) or create_lineage_record(parent_id)
        updated_children = _unique([*parent.children, record.organism_id])
        registry[parent_id] = LineageRecord(
            organism_id=parent.organism_id,
            parents=parent.parents,
            children=updated_children,
            generation=parent.generation,
            mutation_source=parent.mutation_source,
            score=parent.score,
            metadata=parent.metadata,
        )
    return record


def record_child(
    registry: LineageRegistry,
    parent_id: str,
    child_id: str,
    *,
    mutation_source: str | None = None,
    score: float | None = None,
    metadata: Mapping[str, object] | None = None,
) -> LineageRecord:
    """Convenience helper to register a single-parent child."""

    return register_lineage(
        registry,
        child_id,
        parents=[parent_id],
        mutation_source=mutation_source,
        score=score,
        metadata=metadata,
    )


def children_of(
    registry: Mapping[str, LineageRecord], organism_id: str
) -> tuple[str, ...]:
    """Return child identifiers for an organism."""

    record = registry.get(organism_id)
    return record.children if record else ()


def parents_of(
    registry: Mapping[str, LineageRecord], organism_id: str
) -> tuple[str, ...]:
    """Return parent identifiers for an organism."""

    record = registry.get(organism_id)
    return record.parents if record else ()


def lineage_path(
    registry: Mapping[str, LineageRecord], organism_id: str
) -> tuple[str, ...]:
    """Return the first-parent ancestry path ending with ``organism_id``."""

    path: list[str] = []
    current = organism_id
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        path.append(current)
        record = registry.get(current)
        if record is None or not record.parents:
            break
        current = record.parents[0]
    return tuple(reversed(path))


def save_lineage(path: Path, registry: Mapping[str, LineageRecord]) -> None:
    """Persist a lineage registry as deterministic JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {key: registry[key].to_dict() for key in sorted(registry)}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_lineage(path: Path) -> LineageRegistry:
    """Load a lineage registry from JSON, returning an empty registry if absent."""

    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    registry: LineageRegistry = {}
    for key, value in payload.items():
        if not isinstance(value, dict):
            continue
        registry[str(key)] = create_lineage_record(
            str(value.get("organism_id", key)),
            parents=list(value.get("parents", [])),
            children=list(value.get("children", [])),
            generation=int(value.get("generation", 0)),
            mutation_source=value.get("mutation_source"),
            score=value.get("score"),
            metadata=(
                value.get("metadata")
                if isinstance(value.get("metadata"), dict)
                else None
            ),
        )
    return registry
