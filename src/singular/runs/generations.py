"""Generation registry utilities linked to mutation runs."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def get_base_dir() -> Path:
    """Return base life directory from environment."""

    return Path(os.environ.get("SINGULAR_HOME", "."))


def get_generations_path(base_dir: Path | None = None) -> Path:
    """Return the generations JSONL registry path."""

    root = Path(base_dir) if base_dir is not None else get_base_dir()
    return root / "mem" / "generations.jsonl"


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    items: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items


def _next_generation_id(path: Path) -> int:
    items = _read_jsonl(path)
    if not items:
        return 1
    return int(items[-1].get("generation_id", 0)) + 1


def _latest_generation_for_skill(path: Path, *, skill: str) -> dict[str, Any] | None:
    items = _read_jsonl(path)
    for entry in reversed(items):
        if entry.get("skill") == skill:
            return entry
    return None


def record_generation(
    *,
    run_id: str,
    iteration: int,
    skill: str,
    operator: str,
    mutation_diff: str,
    score_base: float,
    score_new: float,
    accepted: bool,
    reason: str,
    parent_hash: str,
    candidate_code: str,
    skill_relative_path: str,
    security_metadata: dict[str, Any],
    base_dir: Path | None = None,
) -> dict[str, Any]:
    """Persist one generation attempt in ``mem/generations.jsonl``."""

    generations_path = get_generations_path(base_dir)
    generation_id = _next_generation_id(generations_path)
    parent = _latest_generation_for_skill(generations_path, skill=skill)

    candidate_hash = hashlib.sha256(candidate_code.encode("utf-8")).hexdigest()
    run_generation_dir = (
        (Path(base_dir) if base_dir is not None else get_base_dir())
        / "runs"
        / run_id
        / "generations"
    )
    run_generation_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = run_generation_dir / f"gen-{generation_id:06d}.py"
    snapshot_path.write_text(candidate_code, encoding="utf-8")

    payload: dict[str, Any] = {
        "generation_id": generation_id,
        "parent_generation_id": parent.get("generation_id") if parent else None,
        "run_id": run_id,
        "iteration": iteration,
        "ts": datetime.utcnow().isoformat(timespec="seconds"),
        "skill": skill,
        "skill_path": skill_relative_path,
        "mutation": {"operator": operator, "diff": mutation_diff},
        "score": {"base": score_base, "new": score_new},
        "verdict": "accepted" if accepted else "rejected",
        "hash": {
            "parent": parent_hash,
            "candidate": candidate_hash,
        },
        "reason": reason,
        "security": security_metadata,
        "snapshot": str(snapshot_path),
        "stable": accepted,
    }
    _append_jsonl(generations_path, payload)
    return payload


def rollback_generation(generation_id: int, *, base_dir: Path | None = None) -> dict[str, Any]:
    """Atomically rollback the skill file to a stable generation snapshot."""

    root = Path(base_dir) if base_dir is not None else get_base_dir()
    generations_path = get_generations_path(root)
    items = _read_jsonl(generations_path)
    generation = next((item for item in items if item.get("generation_id") == generation_id), None)
    if generation is None:
        raise ValueError(f"generation_not_found:{generation_id}")
    if not generation.get("stable"):
        raise ValueError(f"generation_not_stable:{generation_id}")

    snapshot = Path(str(generation.get("snapshot", "")))
    if not snapshot.exists():
        raise ValueError(f"snapshot_not_found:{snapshot}")

    target = root / str(generation.get("skill_path", ""))
    if not str(generation.get("skill_path", "")).strip():
        raise ValueError("generation_missing_skill_path")

    target.parent.mkdir(parents=True, exist_ok=True)
    content = snapshot.read_text(encoding="utf-8")
    fd, tmp_name = tempfile.mkstemp(prefix=target.name, suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, target)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)

    return {
        "generation_id": generation_id,
        "skill_path": str(target),
        "snapshot": str(snapshot),
    }


def retention_policy_text() -> str:
    """Return documented retention policy used for generation metadata."""

    return (
        "Conservation: garder le registre mem/generations.jsonl complet; "
        "archiver les snapshots runs/<run_id>/generations après 30 jours; "
        "purger les snapshots des générations rejetées après archivage validé."
    )
