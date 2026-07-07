"""Philosophical-operational life status contract.

This module intentionally stays separate from :mod:`singular.life.vital`:
``compute_vital_timeline()`` describes observable technical vital state, while
``LifeStatusResult`` carries the life contract exposed to CLI, dashboards, and
reports.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Sequence

if TYPE_CHECKING:  # pragma: no cover - imported only for static typing.
    from singular.life.life_definition import LifeDefinitionConfig


class LifeStatus(str, Enum):
    """Authorized philosophical-operational life statuses."""

    NOT_ALIVE_YET = "not_alive_yet"
    FRAGILE = "fragile"
    ALIVE = "alive"
    DYING = "dying"
    EXTINCT = "extinct"


AUTHORIZED_LIFE_STATUSES: tuple[str, ...] = tuple(status.value for status in LifeStatus)


def _status_value(status: LifeStatus | str) -> str:
    return status.value if isinstance(status, LifeStatus) else str(status)


def _computed_at_value(computed_at: datetime | str) -> str:
    if isinstance(computed_at, datetime):
        return computed_at.isoformat()
    return str(computed_at)


@dataclass(frozen=True)
class LifeStatusResult:
    """Portable result for the life contract shown by CLI, dashboards, and reports."""

    status: LifeStatus | str
    score: float
    explanation: str
    signals: Mapping[str, Any] = field(default_factory=dict)
    missing_signals: Sequence[str] = field(default_factory=tuple)
    evidence: Mapping[str, Any] = field(default_factory=dict)
    computed_at: datetime | str = field(default_factory=lambda: datetime.now(UTC))

    def to_payload(self) -> dict[str, Any]:
        """Return a JSON-serializable payload for CLI, dashboard, and report use."""

        return {
            "status": _status_value(self.status),
            "score": float(self.score),
            "explanation": self.explanation,
            "signals": dict(self.signals),
            "missing_signals": list(self.missing_signals),
            "evidence": dict(self.evidence),
            "computed_at": _computed_at_value(self.computed_at),
        }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    payload.setdefault("_run_file", str(path))
                    rows.append(payload)
    except OSError:
        return []
    return rows


def _load_runs(life_home: Path) -> list[dict[str, Any]]:
    runs_dir = life_home / "runs"
    if not runs_dir.exists():
        return []
    paths = sorted(
        {
            *runs_dir.glob("*.jsonl"),
            *runs_dir.glob("*.jsonl.tmp"),
            *runs_dir.glob("*/events.jsonl"),
        }
    )
    rows: list[dict[str, Any]] = []
    for path in paths:
        if path.is_file():
            rows.extend(_read_jsonl(path))
    return rows


def _as_mapping(value: object | None) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    to_payload = getattr(value, "to_payload", None)
    if callable(to_payload):
        payload = to_payload()
        return dict(payload) if isinstance(payload, Mapping) else {}
    return {
        key: getattr(value, key)
        for key in (
            "name",
            "slug",
            "path",
            "created_at",
            "status",
            "parents",
            "children",
            "lineage_depth",
        )
        if hasattr(value, key)
    }


def _find_registry_entry(life_home: Path) -> dict[str, Any]:
    candidates = [
        life_home.parent / "registry.json",
        life_home.parent.parent / "lives" / "registry.json",
    ]
    for path in candidates:
        registry = _read_json(path)
        lives = registry.get("lives")
        if not isinstance(lives, Mapping):
            continue
        for entry in lives.values():
            current = _as_mapping(entry)
            if (
                Path(str(current.get("path", ""))) == life_home
                or current.get("slug") == life_home.name
            ):
                return current
    return {}


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return (
        parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    )


def _first_timestamp(values: Sequence[Any]) -> datetime | None:
    dates = [dt for dt in (_parse_dt(value) for value in values) if dt is not None]
    return min(dates) if dates else None


def _event_text(row: Mapping[str, Any]) -> str:
    return " ".join(
        str(row.get(key, ""))
        for key in ("event", "phase", "stage", "type", "state", "status")
    ).lower()


def _cycle_count(rows: Sequence[Mapping[str, Any]]) -> int:
    phases = ("veille", "action", "introspection", "sommeil")
    expected = 0
    count = 0
    for row in rows:
        text = _event_text(row)
        phase = phases[expected]
        if phase in text:
            expected += 1
            if expected == len(phases):
                count += 1
                expected = 0
        elif phases[0] in text:
            expected = 1
    return count


def _list_count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def compute_life_status(
    life_home: Path,
    *,
    registry_entry: object | None = None,
    runs: list[dict[str, Any]] | None = None,
    config: "LifeDefinitionConfig | None" = None,
) -> LifeStatusResult:
    """Compute the philosophical-operational life status for one life home.

    The computation is deterministic and accepts injected ``registry_entry``,
    ``runs`` and ``config`` values for tests and dashboards. When omitted, it reads
    the memory files under ``life_home/mem``, the available JSONL run logs under
    ``life_home/runs``, and the matching entry from ``lives/registry.json``.
    """

    from singular.life.life_definition import LifeDefinitionConfig

    cfg = config or LifeDefinitionConfig()
    life_home = Path(life_home)
    mem = life_home / "mem"
    paths = {
        "world_state": mem / "world_state.json",
        "autopsy": mem / "autopsy.json",
        "self_narrative": mem / "self_narrative.json",
        "goals": mem / "goals.json",
        "quests_state": mem / "quests_state.json",
        "generations": mem / "generations.jsonl",
    }
    world_state = _read_json(paths["world_state"])
    autopsy = _read_json(paths["autopsy"])
    narrative = _read_json(paths["self_narrative"])
    goals = _read_json(paths["goals"])
    quests = _read_json(paths["quests_state"])
    generation_rows = _read_jsonl(paths["generations"])
    run_rows = runs if runs is not None else _load_runs(life_home)
    registry = (
        _as_mapping(registry_entry)
        if registry_entry is not None
        else _find_registry_entry(life_home)
    )

    optional_files = {"goals", "generations"}
    missing = [
        name
        for name, path in paths.items()
        if name not in optional_files and not path.exists()
    ]
    if runs is None and not (life_home / "runs").exists():
        missing.append("runs")
    if not registry:
        missing.append("registry_entry")

    identity = (
        narrative.get("identity")
        if isinstance(narrative.get("identity"), Mapping)
        else {}
    )
    identity_name = str(identity.get("name") or registry.get("name") or "").strip()
    born_at = identity.get("born_at") or registry.get("created_at")
    persistent_identity = bool(identity_name and (born_at or registry.get("slug")))

    generation_registry = bool(generation_rows) or any(
        "mutation" in _event_text(row) or "generation" in _event_text(row)
        for row in run_rows
    )

    observed_cycles = _cycle_count(run_rows)
    stable_cycle = observed_cycles >= cfg.thresholds.minimum_observed_cycles

    weights = goals.get("weights") if isinstance(goals.get("weights"), Mapping) else {}
    active_goal_count = sum(
        1
        for value in weights.values()
        if isinstance(value, (int, float)) and float(value) > 0
    )
    active_quests = (
        quests.get("active") if isinstance(quests.get("active"), list) else []
    )
    paused_quests = (
        quests.get("paused") if isinstance(quests.get("paused"), list) else []
    )
    intrinsic_quest_count = sum(
        1
        for item in active_quests + paused_quests
        if isinstance(item, Mapping) and item.get("origin") == "intrinsic"
    )
    intrinsic_goals = (
        active_goal_count > 0 or intrinsic_quest_count > 0 or bool(goals.get("history"))
    )

    children = (
        registry.get("children")
        if isinstance(registry.get("children"), list | tuple)
        else []
    )
    reproduction_events = [
        row
        for row in run_rows
        if any(
            token in _event_text(row)
            for token in ("birth", "reproduction", "child", "offspring")
        )
    ]
    reproduction_possible = bool(
        children
        or reproduction_events
        or registry.get("lineage_depth", 0) is not None
        and persistent_identity
        and not autopsy
    )
    reproduction_done = bool(children or reproduction_events)

    period_dates: list[Any] = [born_at]
    for period in (
        narrative.get("life_periods", [])
        if isinstance(narrative.get("life_periods"), list)
        else []
    ):
        if isinstance(period, Mapping):
            period_dates.extend([period.get("start_at"), period.get("end_at")])
    period_dates.extend(
        row.get("ts") or row.get("time") or row.get("timestamp") for row in run_rows
    )
    first_seen = _first_timestamp(period_dates)
    age_days = (datetime.now(UTC) - first_seen).days if first_seen else 0
    narrative_has_content = bool(
        narrative.get("current_heading") or _list_count(narrative.get("life_periods"))
    )
    narrative_continuity = (
        narrative_has_content
        and age_days >= cfg.thresholds.minimum_narrative_trajectory_days
    )

    registry_status = str(registry.get("status", "")).lower()
    extinction_events = [
        row
        for row in run_rows
        if any(token in _event_text(row) for token in ("extinct", "death", "terminal"))
    ]
    terminal = (
        bool(autopsy)
        or registry_status in {"extinct", "dead", "stopped", "terminal"}
        or bool(extinction_events)
    )

    criteria = {
        "persistent_identity": (cfg.criteria.persistent_identity, persistent_identity),
        "generation_registry": (cfg.criteria.generation_registry, generation_registry),
        "stable_cycle": (cfg.criteria.stable_cycle, stable_cycle),
        "intrinsic_goals": (cfg.criteria.intrinsic_goals, intrinsic_goals),
        "reproduction_capability": (
            cfg.criteria.reproduction_capability,
            reproduction_possible or reproduction_done,
        ),
        "narrative_continuity": (
            cfg.criteria.narrative_continuity,
            narrative_continuity,
        ),
    }
    enabled = [
        (name, value) for name, (required, value) in criteria.items() if required
    ]
    score = (
        0.0 if not enabled else sum(1.0 for _, value in enabled if value) / len(enabled)
    )
    if terminal:
        score = min(score, 0.2 if registry_status == "extinct" or autopsy else 0.4)
        status = (
            LifeStatus.EXTINCT
            if registry_status == "extinct" or autopsy
            else LifeStatus.DYING
        )
    elif not persistent_identity and not run_rows:
        status = LifeStatus.NOT_ALIVE_YET
    elif score >= cfg.thresholds.alive_minimum_score:
        status = LifeStatus.ALIVE
    elif score >= cfg.thresholds.fragile_minimum_score:
        status = LifeStatus.FRAGILE
    else:
        status = LifeStatus.NOT_ALIVE_YET

    positives = [name for name, value in enabled if value]
    negatives = [name for name, value in enabled if not value]
    explanation = f"Statut {status.value}: {len(positives)}/{len(enabled)} sous-signaux configurés sont établis."
    if negatives:
        explanation += " Manquants ou insuffisants: " + ", ".join(negatives) + "."
    if terminal:
        explanation += " Un signal d'extinction ou d'état terminal domine l'évaluation."

    signals = {
        "persistent_identity": persistent_identity,
        "generation_registry": generation_registry,
        "stable_cycle": stable_cycle,
        "observed_cycles": observed_cycles,
        "intrinsic_goals": intrinsic_goals,
        "active_goal_count": active_goal_count,
        "intrinsic_quest_count": intrinsic_quest_count,
        "reproduction_possible": reproduction_possible,
        "reproduction_done": reproduction_done,
        "narrative_continuity": narrative_continuity,
        "narrative_age_days": age_days,
        "terminal": terminal,
        "extinction": status is LifeStatus.EXTINCT,
    }
    evidence = {
        "files": {key: str(path) for key, path in paths.items() if path.exists()},
        "registry": {
            key: registry.get(key)
            for key in (
                "slug",
                "name",
                "status",
                "created_at",
                "children",
                "lineage_depth",
            )
            if key in registry
        },
        "runs_count": len(run_rows),
        "generations_count": len(generation_rows),
        "extinction_events_count": len(extinction_events),
        "reproduction_events_count": len(reproduction_events),
        "thresholds": {
            "minimum_narrative_trajectory_days": cfg.thresholds.minimum_narrative_trajectory_days,
            "minimum_observed_cycles": cfg.thresholds.minimum_observed_cycles,
            "alive_minimum_score": cfg.thresholds.alive_minimum_score,
            "fragile_minimum_score": cfg.thresholds.fragile_minimum_score,
        },
    }
    return LifeStatusResult(
        status=status,
        score=round(score, 4),
        explanation=explanation,
        signals=signals,
        missing_signals=tuple(missing),
        evidence=evidence,
    )
