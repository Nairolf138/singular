"""Memory management utilities.

JSON is used for most memory files.  The ``values.yaml`` file is only handled
when the optional :mod:`PyYAML <yaml>` package is available.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

if os.name == "nt":
    import msvcrt
else:
    import fcntl

from .events import Event, EventBus
from .memory_layers import MemoryLayerService, build_backend

_MEMORY_LAYER_SERVICE: MemoryLayerService | None = None


def get_base_dir() -> Path:
    """Return the base directory for persistent files."""
    return Path(os.environ.get("SINGULAR_HOME", "."))


def get_mem_dir() -> Path:
    """Return the base memory directory."""
    return get_base_dir() / "mem"


def get_memory_layers_dir() -> Path:
    """Return the directory containing layered memory storage."""

    return get_mem_dir() / "layers"


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


def get_skill_snapshots_dir() -> Path:
    """Return the directory storing skill lifecycle snapshots."""
    return get_mem_dir() / "skills_snapshots"


def get_psyche_file() -> Path:
    """Return the path to the psyche JSON file."""
    return get_mem_dir() / "psyche.json"


def _ensure_dir(path: Path) -> None:
    """Ensure the parent directory of ``path`` exists."""
    path.parent.mkdir(parents=True, exist_ok=True)


def _atomic_write_text(path: Path, data: str) -> None:
    """Atomically write ``data`` to ``path``."""
    _ensure_dir(path)
    tmp = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    )
    try:
        with tmp:
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp.name, path)
    finally:
        try:
            os.unlink(tmp.name)
        except FileNotFoundError:
            pass


def _append_jsonl_line(path: Path, payload: dict[str, Any]) -> None:
    """Safely append one JSON line with cross-platform file locking."""

    _ensure_dir(path)
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+b") as lock_file:
        if os.name == "nt":
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        else:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            with path.open("a", encoding="utf-8") as file:
                file.write(line)
                file.flush()
                os.fsync(file.fileno())
        finally:
            if os.name == "nt":
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def ensure_memory_structure(mem_dir: Path | str | None = None) -> None:
    """Create the memory directory structure if it does not exist."""
    if mem_dir is None:
        mem_dir = get_mem_dir()
    mem_dir = Path(mem_dir)
    mem_dir.mkdir(parents=True, exist_ok=True)
    (mem_dir / "profile.json").touch(exist_ok=True)
    (mem_dir / "values.yaml").touch(exist_ok=True)
    (mem_dir / "episodic.jsonl").touch(exist_ok=True)
    (mem_dir / "generations.jsonl").touch(exist_ok=True)
    (mem_dir / "skills.json").touch(exist_ok=True)
    (mem_dir / "psyche.json").touch(exist_ok=True)
    (mem_dir / "layers").mkdir(parents=True, exist_ok=True)


def get_memory_layer_service() -> MemoryLayerService:
    """Return the singleton memory layer service."""

    global _MEMORY_LAYER_SERVICE
    if _MEMORY_LAYER_SERVICE is None:
        _MEMORY_LAYER_SERVICE = MemoryLayerService(
            build_backend(root=get_memory_layers_dir())
        )
    return _MEMORY_LAYER_SERVICE


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
    _atomic_write_text(path, json.dumps(profile))


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
    if not isinstance(data, dict):
        return {}
    return data


def write_values(values: dict[str, Any], path: Path | str | None = None) -> None:
    """Write the values YAML file.

    Requires :mod:`pyyaml` to be installed.
    """
    if path is None:
        path = get_values_file()
    path = Path(path)
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "PyYAML is required to write values. Please install PyYAML."
        ) from exc
    _atomic_write_text(path, yaml.safe_dump(values))


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


def add_episode(
    episode: dict[str, Any],
    path: Path | str | None = None,
    mood_styles: Mapping[str | None, Callable[[str], str]] | None = None,
) -> None:
    """Append a new episode to the episodic memory file.

    If ``mood_styles`` is provided and the episode contains a ``mood`` field,
    the corresponding rendering function is applied to the mood value before the
    episode is serialized.
    """

    if mood_styles and (mood := episode.get("mood")) is not None:
        style = mood_styles.get(mood) or mood_styles.get(None) or (lambda x: x)
        episode = {**episode, "mood": style(mood)}

    if path is None:
        path = get_episodic_file()
    path = Path(path)
    _append_jsonl_line(path, episode)
    try:
        get_memory_layer_service().ingest_episode(episode)
    except Exception:
        # Layered memory is best effort to preserve compatibility.
        pass


def add_procedural_memory(result: dict[str, Any]) -> None:
    """Store mutation/run outcomes into procedural memory."""

    try:
        get_memory_layer_service().ingest_mutation_result(result)
    except Exception:
        # Layered memory is best effort to preserve compatibility.
        pass


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
    _atomic_write_text(path, json.dumps(skills))


def update_score(
    skill: str, score: float, path: Path | str | None = None
) -> dict[str, Any]:
    """Update a skill score in the skills file.

    Existing note text for ``skill`` is preserved if present.
    """

    skills = read_skills(path)
    entry = skills.get(skill)
    if isinstance(entry, dict):
        entry["score"] = score
    else:
        entry = {"score": score}
    skills[skill] = entry
    write_skills(skills, path)
    return skills


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_skill_entry(entry: Any) -> dict[str, Any]:
    if isinstance(entry, (int, float)):
        entry = {"score": float(entry)}
    if not isinstance(entry, dict):
        entry = {}
    score = float(entry.get("score", 0.0))
    metrics = entry.get("metrics") if isinstance(entry.get("metrics"), dict) else {}
    lifecycle = entry.get("lifecycle") if isinstance(entry.get("lifecycle"), dict) else {}
    entry["score"] = score
    entry["metrics"] = {
        "usage_count": int(metrics.get("usage_count", 0) or 0),
        "total_gain": float(metrics.get("total_gain", 0.0) or 0.0),
        "average_gain": float(metrics.get("average_gain", 0.0) or 0.0),
        "total_cost": float(metrics.get("total_cost", 0.0) or 0.0),
        "average_cost": float(metrics.get("average_cost", 0.0) or 0.0),
        "failure_count": int(metrics.get("failure_count", 0) or 0),
        "last_used_at": metrics.get("last_used_at"),
    }
    state = lifecycle.get("state")
    if not isinstance(state, str) or state not in {
        "active",
        "dormant",
        "archived",
        "temporarily_disabled",
        "deleted",
    }:
        state = "active"
    entry["lifecycle"] = {
        "state": state,
        "state_reason": lifecycle.get("state_reason"),
        "disabled_until": lifecycle.get("disabled_until"),
        "last_transition_at": lifecycle.get("last_transition_at"),
        "snapshot_path": lifecycle.get("snapshot_path"),
    }
    return entry


def record_skill_metric(
    skill: str,
    *,
    gain: float,
    cost: float,
    success: bool,
    path: Path | str | None = None,
) -> dict[str, Any]:
    """Record longitudinal skill metrics (usage, gain, cost, failures)."""

    skills = read_skills(path)
    entry = _normalize_skill_entry(skills.get(skill))
    metrics = entry["metrics"]
    lifecycle = entry["lifecycle"]

    metrics["usage_count"] += 1
    metrics["total_gain"] += float(gain)
    metrics["total_cost"] += max(float(cost), 0.0)
    if not success:
        metrics["failure_count"] += 1
    usage_count = max(int(metrics["usage_count"]), 1)
    metrics["average_gain"] = metrics["total_gain"] / usage_count
    metrics["average_cost"] = metrics["total_cost"] / usage_count
    metrics["last_used_at"] = _utc_now_iso()

    lifecycle["state"] = "active"
    lifecycle["state_reason"] = "recent_usage"
    lifecycle["disabled_until"] = None
    lifecycle["last_transition_at"] = _utc_now_iso()

    skills[skill] = entry
    write_skills(skills, path)
    return skills


def apply_skill_maintenance(
    *,
    dormant_after_days: int = 14,
    archive_after_days: int = 30,
    path: Path | str | None = None,
) -> dict[str, Any]:
    """Apply lifecycle rules: inactive -> dormant -> archived."""

    skills = read_skills(path)
    now = datetime.now(timezone.utc)
    for key, raw_entry in list(skills.items()):
        entry = _normalize_skill_entry(raw_entry)
        lifecycle = entry["lifecycle"]
        if lifecycle["state"] in {"deleted", "temporarily_disabled"}:
            skills[key] = entry
            continue
        last_used_raw = entry["metrics"].get("last_used_at")
        if isinstance(last_used_raw, str):
            try:
                last_used_at = datetime.fromisoformat(last_used_raw.replace("Z", "+00:00"))
            except ValueError:
                last_used_at = None
        else:
            last_used_at = None
        if last_used_at is None:
            skills[key] = entry
            continue
        idle = now - last_used_at
        if idle >= timedelta(days=archive_after_days):
            lifecycle["state"] = "archived"
            lifecycle["state_reason"] = "inactive_too_long"
            lifecycle["last_transition_at"] = _utc_now_iso()
        elif idle >= timedelta(days=dormant_after_days):
            lifecycle["state"] = "dormant"
            lifecycle["state_reason"] = "inactive"
            lifecycle["last_transition_at"] = _utc_now_iso()
        else:
            lifecycle["state"] = "active"
            lifecycle["state_reason"] = "healthy_activity"
            lifecycle["last_transition_at"] = _utc_now_iso()
        skills[key] = entry
    write_skills(skills, path)
    return skills


def temporarily_disable_skill(
    skill: str,
    *,
    duration_hours: int,
    reason: str,
    path: Path | str | None = None,
) -> dict[str, Any]:
    """Temporarily disable a skill without deleting it."""
    skills = read_skills(path)
    entry = _normalize_skill_entry(skills.get(skill))
    lifecycle = entry["lifecycle"]
    lifecycle["state"] = "temporarily_disabled"
    lifecycle["state_reason"] = reason
    lifecycle["disabled_until"] = (
        datetime.now(timezone.utc) + timedelta(hours=max(duration_hours, 1))
    ).isoformat()
    lifecycle["last_transition_at"] = _utc_now_iso()
    skills[skill] = entry
    write_skills(skills, path)
    return skills


def restore_skill(skill: str, path: Path | str | None = None) -> dict[str, Any]:
    """Restore an archived/dormant/disabled skill to active state."""
    skills = read_skills(path)
    if skill not in skills:
        raise KeyError(f"unknown skill: {skill}")
    entry = _normalize_skill_entry(skills[skill])
    lifecycle = entry["lifecycle"]
    lifecycle["state"] = "active"
    lifecycle["state_reason"] = "restored"
    lifecycle["disabled_until"] = None
    lifecycle["last_transition_at"] = _utc_now_iso()
    skills[skill] = entry
    write_skills(skills, path)
    return skills


def controlled_delete_skill(
    skill: str,
    *,
    reason: str,
    path: Path | str | None = None,
    snapshots_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Governed deletion: keep a snapshot and tombstone instead of hard removal."""

    skills = read_skills(path)
    if skill not in skills:
        raise KeyError(f"unknown skill: {skill}")
    entry = _normalize_skill_entry(skills[skill])
    snapshots = Path(snapshots_dir) if snapshots_dir is not None else get_skill_snapshots_dir()
    snapshots.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot_path = snapshots / f"{skill}-{ts}.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "skill": skill,
                "deleted_at": _utc_now_iso(),
                "reason": reason,
                "snapshot": entry,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    entry["lifecycle"]["state"] = "deleted"
    entry["lifecycle"]["state_reason"] = reason
    entry["lifecycle"]["snapshot_path"] = str(snapshot_path)
    entry["lifecycle"]["last_transition_at"] = _utc_now_iso()
    skills[skill] = entry
    write_skills(skills, path)
    return skills


def update_note(
    skill: str, note: str, path: Path | str | None = None
) -> dict[str, Any]:
    """Update or add a free-form note for ``skill`` in the skills file."""

    skills = read_skills(path)
    entry = skills.get(skill)
    if isinstance(entry, dict):
        entry["note"] = note
    else:
        entry = {"score": 0.0, "note": note}
    skills[skill] = entry
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
    _atomic_write_text(path, json.dumps(state))


_REGISTERED_MEMORY_BUS_IDS: set[int] = set()


def _consolidate_signal_event(event: Event) -> None:
    payload = event.payload
    signals = payload.get("signals", {})
    if isinstance(signals, dict):
        add_episode({"event": "perception", **signals})


def _consolidate_decision_event(event: Event) -> None:
    payload = event.payload
    decision = payload.get("decision", {})
    context = payload.get("context", {})
    if isinstance(decision, dict):
        episode = {"event": "decision", **decision}
        if isinstance(context, dict):
            episode.update({"context": context})
        add_episode(episode)


def _consolidate_applied_mutation(event: Event) -> None:
    payload = event.payload
    key = payload.get("skill")
    score_new = payload.get("score_new")
    score_base = payload.get("score_base")
    ms_new = payload.get("ms_new")
    if isinstance(key, str) and isinstance(score_new, (int, float)):
        update_score(key, float(score_new))
        gain = 0.0
        if isinstance(score_base, (int, float)):
            gain = float(score_base) - float(score_new)
        cost = float(ms_new) if isinstance(ms_new, (int, float)) else 0.0
        record_skill_metric(key, gain=gain, cost=cost, success=True)
    add_procedural_memory({"event": "loop_mutation", **payload, "accepted": True})


def _consolidate_rejected_mutation(event: Event) -> None:
    payload = event.payload
    key = payload.get("skill")
    if isinstance(key, str):
        score_base = payload.get("score_base")
        score_new = payload.get("score_new")
        ms_new = payload.get("ms_new")
        gain = 0.0
        if isinstance(score_base, (int, float)) and isinstance(score_new, (int, float)):
            gain = float(score_base) - float(score_new)
        cost = float(ms_new) if isinstance(ms_new, (int, float)) else 0.0
        record_skill_metric(key, gain=gain, cost=cost, success=False)
    add_procedural_memory({"event": "loop_mutation", **payload, "accepted": False})


def register_memory_event_handlers(bus: EventBus) -> None:
    """Subscribe memory consolidation handlers once for the given bus."""

    identity = id(bus)
    if identity in _REGISTERED_MEMORY_BUS_IDS:
        return

    bus.subscribe("signal.captured", _consolidate_signal_event)
    bus.subscribe("decision.made", _consolidate_decision_event)
    bus.subscribe("mutation.applied", _consolidate_applied_mutation)
    bus.subscribe("mutation.rejected", _consolidate_rejected_mutation)
    _REGISTERED_MEMORY_BUS_IDS.add(identity)
