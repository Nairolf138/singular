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

from singular.life.vital import compute_vital_timeline

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


def _read_json_object(path: Path) -> dict[str, object]:
    """Read a JSON file only when its root payload is an object."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _read_json(path: Path) -> dict[str, Any]:
    return _read_json_object(path)


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


REQUIRED_CYCLE_PHASES = ("veille", "action", "introspection", "sommeil")
TERMINAL_PHASE_TOKENS = ("extinct", "extinction", "death", "terminal", "dying", "stop")


def _row_phase(row: Mapping[str, Any]) -> str | None:
    text = _event_text(row)
    for phase in REQUIRED_CYCLE_PHASES:
        if phase in text:
            return phase
    return None


def _row_timestamp(row: Mapping[str, Any]) -> str | None:
    for key in ("ts", "time", "timestamp", "created_at"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _cycle_analysis(
    rows: Sequence[Mapping[str, Any]],
    *,
    required_cycles: int,
    tolerated_anomalies: int,
) -> dict[str, Any]:
    expected = 0
    observed_cycles = 0
    anomalies = 0
    current_cycle: list[dict[str, Any]] = []
    completed_cycles: list[list[dict[str, Any]]] = []
    phase_events = 0
    terminal_events: list[dict[str, Any]] = []

    for index, row in enumerate(rows):
        text = _event_text(row)
        terminal = any(token in text for token in TERMINAL_PHASE_TOKENS)
        if terminal:
            terminal_events.append(
                {
                    "index": index,
                    "event": row.get("event"),
                    "phase": row.get("phase"),
                    "ts": _row_timestamp(row),
                }
            )
        phase = _row_phase(row)
        if phase is None:
            continue
        phase_events += 1
        expected_phase = REQUIRED_CYCLE_PHASES[expected]
        event_evidence = {
            "phase": phase,
            "index": index,
            "event": row.get("event"),
            "ts": _row_timestamp(row),
        }
        if phase == expected_phase:
            current_cycle.append(event_evidence)
            expected += 1
            if expected == len(REQUIRED_CYCLE_PHASES):
                observed_cycles += 1
                completed_cycles.append(current_cycle)
                current_cycle = []
                expected = 0
        elif phase == REQUIRED_CYCLE_PHASES[0]:
            if current_cycle:
                anomalies += 1
            current_cycle = [event_evidence]
            expected = 1
        else:
            anomalies += 1

    missing_phases = list(REQUIRED_CYCLE_PHASES[expected:]) if expected else []
    if missing_phases:
        anomalies += len(missing_phases)

    recent_window = max(
        len(REQUIRED_CYCLE_PHASES), required_cycles * len(REQUIRED_CYCLE_PHASES)
    )
    recent_rows = list(rows)[-recent_window:] if recent_window > 0 else list(rows)
    recent_phase_count = sum(1 for row in recent_rows if _row_phase(row) is not None)
    recent_terminal_count = sum(
        1
        for row in recent_rows
        if any(token in _event_text(row) for token in TERMINAL_PHASE_TOKENS)
    )
    terminal_dominates = bool(
        recent_terminal_count and recent_terminal_count >= max(1, recent_phase_count)
    )
    ok = (
        observed_cycles >= required_cycles
        and anomalies <= tolerated_anomalies
        and not terminal_dominates
    )
    return {
        "ok": ok,
        "observed_cycles": observed_cycles,
        "required_cycles": required_cycles,
        "tolerated_anomalies": tolerated_anomalies,
        "anomalies": anomalies,
        "missing_phases": missing_phases,
        "terminal_dominates": terminal_dominates,
        "recent_terminal_events_count": recent_terminal_count,
        "recent_phase_events_count": recent_phase_count,
        "terminal_events_count": len(terminal_events),
        "last_cycles": (
            completed_cycles[-required_cycles:]
            if required_cycles > 0
            else completed_cycles[-3:]
        ),
        "current_incomplete_cycle": current_cycle,
    }


def _cycle_count(rows: Sequence[Mapping[str, Any]]) -> int:
    return int(
        _cycle_analysis(rows, required_cycles=0, tolerated_anomalies=10**9)[
            "observed_cycles"
        ]
    )


def _health_score_from_payload(payload: Mapping[str, Any]) -> float | None:
    health = payload.get("health")
    if isinstance(health, Mapping) and isinstance(health.get("score"), (int, float)):
        return float(health["score"])
    global_health = payload.get("global_health")
    if isinstance(global_health, Mapping) and isinstance(
        global_health.get("score"), (int, float)
    ):
        return float(global_health["score"])
    return None


def _accepted_value(row: Mapping[str, Any]) -> bool | None:
    accepted = row.get("accepted")
    if not isinstance(accepted, bool):
        accepted = row.get("ok")
    return accepted if isinstance(accepted, bool) else None


def _failure_streak(rows: Sequence[Mapping[str, Any]]) -> int:
    current = 0
    longest = 0
    for row in rows:
        accepted = _accepted_value(row)
        if accepted is False:
            current += 1
            longest = max(longest, current)
        elif accepted is True:
            current = 0
    return longest


def _list_count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _signal(
    ok: bool, score: float, reason: str, evidence: Mapping[str, object] | None = None
) -> dict[str, object]:
    return {
        "ok": bool(ok),
        "score": float(score),
        "reason": reason,
        "evidence": dict(evidence or {}),
    }


def _extract_identity_signal(self_narrative: dict) -> dict:
    identity = (
        self_narrative.get("identity")
        if isinstance(self_narrative.get("identity"), Mapping)
        else {}
    )
    name = (
        str(identity.get("name") or "").strip() if isinstance(identity, Mapping) else ""
    )
    born_at = identity.get("born_at") if isinstance(identity, Mapping) else None
    slug = identity.get("slug") if isinstance(identity, Mapping) else None
    ok = bool(name and (born_at or slug))
    missing = [
        label
        for label, present in (
            ("name", bool(name)),
            ("born_at_or_slug", bool(born_at or slug)),
        )
        if not present
    ]
    return _signal(
        ok,
        1.0 if ok else 0.0,
        (
            "persistent identity found"
            if ok
            else "identity is incomplete: " + ", ".join(missing)
        ),
        {"name": name, "born_at": born_at, "slug": slug, "missing": missing},
    )


def _extract_narrative_continuity_signal(
    self_narrative: dict, threshold_days: int
) -> dict:
    period_dates: list[Any] = []
    identity = (
        self_narrative.get("identity")
        if isinstance(self_narrative.get("identity"), Mapping)
        else {}
    )
    if isinstance(identity, Mapping):
        period_dates.append(identity.get("born_at"))
    periods = (
        self_narrative.get("life_periods")
        if isinstance(self_narrative.get("life_periods"), list)
        else []
    )
    for period in periods:
        if isinstance(period, Mapping):
            period_dates.extend([period.get("start_at"), period.get("end_at")])
    first_seen = _first_timestamp(period_dates)
    age_days = (datetime.now(UTC) - first_seen).days if first_seen else 0
    has_content = bool(
        self_narrative.get("current_heading")
        or _list_count(self_narrative.get("life_periods"))
    )
    ok = bool(has_content and age_days >= threshold_days)
    return _signal(
        ok,
        1.0 if ok else 0.0,
        (
            "narrative continuity threshold reached"
            if ok
            else "narrative content or age is insufficient"
        ),
        {
            "age_days": age_days,
            "threshold_days": threshold_days,
            "has_content": has_content,
            "periods_count": len(periods),
        },
    )


def _is_self_generated_intrinsic_goal(item: Mapping[str, object]) -> bool:
    return (
        item.get("source") == "intrinsic"
        or item.get("origin") in {"intrinsic", "self_generated"}
        or item.get("kind") == "intrinsic_goal"
    )


def _is_active_intrinsic_goal(item: Mapping[str, object]) -> bool:
    if not _is_self_generated_intrinsic_goal(item):
        return False
    status = str(item.get("status") or item.get("state") or "active").lower()
    return status in {"active", "maintained", "renewed", "resumed"}


def _extract_goal_signal(goals: dict, quests: dict, runs: list[dict]) -> dict:
    weights = goals.get("weights") if isinstance(goals.get("weights"), Mapping) else {}
    active_goal_count = sum(
        1
        for value in weights.values()
        if isinstance(value, (int, float)) and float(value) > 0
    )
    intrinsic_goal_weight_count = (
        active_goal_count if _is_active_intrinsic_goal(goals) else 0
    )
    history = goals.get("history") if isinstance(goals.get("history"), list) else []
    renewed_intrinsic_goal_count = sum(
        1
        for item in history
        if isinstance(item, Mapping) and _is_active_intrinsic_goal(item)
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
        if isinstance(item, Mapping) and _is_active_intrinsic_goal(item)
    )
    run_goal_events = [
        row
        for row in runs
        if any(token in _event_text(row) for token in ("goal", "quest", "objective"))
    ]
    ok = (
        intrinsic_goal_weight_count > 0
        or intrinsic_quest_count > 0
        or renewed_intrinsic_goal_count > 0
    )
    return _signal(
        ok,
        1.0 if ok else 0.0,
        (
            "active self-generated intrinsic goals are present"
            if ok
            else "no active self-generated intrinsic goal evidence found"
        ),
        {
            "active_goal_count": active_goal_count,
            "intrinsic_goal_weight_count": intrinsic_goal_weight_count,
            "intrinsic_quest_count": intrinsic_quest_count,
            "renewed_intrinsic_goal_count": renewed_intrinsic_goal_count,
            "history_count": _list_count(goals.get("history")),
            "run_goal_events_count": len(run_goal_events),
        },
    )


def _extract_generation_signal(life_home: Path, runs: list[dict]) -> dict:
    generation_rows = _read_jsonl(Path(life_home) / "mem" / "generations.jsonl")
    run_generation_events = [
        row
        for row in runs
        if "mutation" in _event_text(row) or "generation" in _event_text(row)
    ]
    ok = bool(generation_rows or run_generation_events)
    return _signal(
        ok,
        1.0 if ok else 0.0,
        (
            "generation registry evidence found"
            if ok
            else "no generation registry evidence found"
        ),
        {
            "generations_count": len(generation_rows),
            "run_generation_events_count": len(run_generation_events),
        },
    )


def _extract_extinction_signal(
    autopsy: dict, registry_status: str | None, runs: list[dict]
) -> dict:
    status = str(registry_status or "").lower()
    extinction_events = [
        row
        for row in runs
        if any(token in _event_text(row) for token in ("extinct", "death", "terminal"))
    ]
    confirmed_events = [
        row
        for row in runs
        if any(token in _event_text(row) for token in ("extinct", "death"))
    ]
    ok = bool(autopsy) or status == "extinct" or bool(confirmed_events)
    return _signal(
        ok,
        1.0 if ok else 0.0,
        "extinction evidence found" if ok else "no confirmed extinction evidence found",
        {
            "autopsy_present": bool(autopsy),
            "registry_status": registry_status,
            "extinction_events_count": len(extinction_events),
            "confirmed_extinction_events_count": len(confirmed_events),
        },
    )


def _valid_string_items(value: Any) -> list[str]:
    if not isinstance(value, list | tuple | set):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _lineage_descendants_from_registry(
    *, life_home: Path, registry: Mapping[str, Any]
) -> list[str]:
    descendants = _valid_string_items(registry.get("children"))
    slug = str(registry.get("slug") or life_home.name).strip()
    lineage_paths = [
        life_home / "mem" / "lineage.json",
        life_home.parent / "lineage.json",
    ]
    for path in lineage_paths:
        lineage = _read_json(path)
        if not lineage:
            continue
        candidate_ids = [slug, str(registry.get("name") or "").strip()]
        for candidate_id in candidate_ids:
            record = lineage.get(candidate_id)
            if isinstance(record, Mapping):
                descendants.extend(_valid_string_items(record.get("children")))
        for record_id, record in lineage.items():
            if not isinstance(record, Mapping):
                continue
            parents = _valid_string_items(record.get("parents"))
            if slug and slug in parents:
                descendants.append(str(record.get("organism_id") or record_id).strip())
    return sorted({item for item in descendants if item})


def _generation_descendants(generation_rows: Sequence[Mapping[str, Any]]) -> list[str]:
    descendants: list[str] = []
    for row in generation_rows:
        parent_generation_id = row.get("parent_generation_id")
        if parent_generation_id in (None, "", 0):
            continue
        child = (
            row.get("child")
            or row.get("child_id")
            or row.get("clone")
            or row.get("clone_id")
            or row.get("generation_id")
        )
        if child not in (None, ""):
            descendants.append(str(child).strip())
    return sorted({item for item in descendants if item})


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
    narrative_with_registry_identity = dict(narrative)
    narrative_with_registry_identity["identity"] = {
        **dict(identity),
        "name": identity.get("name") or registry.get("name"),
        "born_at": identity.get("born_at") or registry.get("created_at"),
        "slug": identity.get("slug") or registry.get("slug"),
    }
    identity_signal = _extract_identity_signal(narrative_with_registry_identity)
    born_at = narrative_with_registry_identity["identity"].get("born_at")
    persistent_identity = bool(identity_signal["ok"])

    generation_signal = _extract_generation_signal(life_home, run_rows)
    generation_registry = bool(generation_signal["ok"])

    cycle_evidence = _cycle_analysis(
        run_rows,
        required_cycles=cfg.thresholds.minimum_observed_cycles,
        tolerated_anomalies=cfg.thresholds.maximum_cycle_anomalies,
    )
    observed_cycles = int(cycle_evidence["observed_cycles"])
    stable_cycle = bool(cycle_evidence["ok"])

    goal_signal = _extract_goal_signal(goals, quests, run_rows)
    goal_evidence = goal_signal.get("evidence", {})
    active_goal_count = (
        int(goal_evidence.get("active_goal_count", 0))
        if isinstance(goal_evidence, Mapping)
        else 0
    )
    intrinsic_quest_count = (
        int(goal_evidence.get("intrinsic_quest_count", 0))
        if isinstance(goal_evidence, Mapping)
        else 0
    )
    intrinsic_goals = bool(goal_signal["ok"])

    children = _valid_string_items(registry.get("children"))
    lineage_descendants = _lineage_descendants_from_registry(
        life_home=life_home,
        registry=registry,
    )
    generation_descendants = _generation_descendants(generation_rows)
    detected_descendants = sorted(
        {*children, *lineage_descendants, *generation_descendants}
    )
    reproduction_events = [
        row
        for row in run_rows
        if any(
            token in _event_text(row)
            for token in ("birth", "reproduction", "child", "offspring", "clone")
        )
    ]

    world_state = _read_json(paths["world_state"])
    mutation_rows = [row for row in run_rows if "score_new" in row]
    success_records = [
        row
        for row in run_rows
        if "score_new" in row or isinstance(_accepted_value(row), bool)
    ]
    ok_count = sum(1 for row in success_records if _accepted_value(row) is True)
    health_scores = [
        score
        for score in (
            _health_score_from_payload(row) for row in [*run_rows, world_state]
        )
        if score is not None
    ]

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
    narrative_continuity_signal = _extract_narrative_continuity_signal(
        narrative_with_registry_identity,
        cfg.thresholds.minimum_narrative_trajectory_days,
    )
    narrative_continuity = bool(
        narrative_has_content
        and age_days >= cfg.thresholds.minimum_narrative_trajectory_days
    ) or bool(narrative_continuity_signal["ok"])

    registry_status = str(registry.get("status", "")).lower()
    extinction_signal = _extract_extinction_signal(
        autopsy, registry_status or None, run_rows
    )
    extinction_evidence = extinction_signal.get("evidence", {})
    extinction_events_count = (
        int(extinction_evidence.get("extinction_events_count", 0))
        if isinstance(extinction_evidence, Mapping)
        else 0
    )
    confirmed_extinction_events_count = (
        int(extinction_evidence.get("confirmed_extinction_events_count", 0))
        if isinstance(extinction_evidence, Mapping)
        else 0
    )
    vital_timeline = compute_vital_timeline(
        age=len(mutation_rows),
        current_health=health_scores[-1] if health_scores else None,
        failure_rate=(
            (1 - (ok_count / len(success_records))) if success_records else None
        ),
        failure_streak=_failure_streak(success_records),
        extinction_seen=bool(extinction_signal["ok"]),
        registry_status=registry_status or None,
    )
    vital_state = str(vital_timeline.get("state", ""))
    terminal = vital_state in {"terminal", "extinct"}
    reproduction_eligible = vital_timeline.get("reproduction_eligible") is True
    reproduction_capability = bool(
        reproduction_eligible or reproduction_events or detected_descendants
    )
    reproduction_done = bool(reproduction_events or detected_descendants)
    reproduction_possible = reproduction_capability

    criteria = {
        "persistent_identity": (cfg.criteria.persistent_identity, persistent_identity),
        "generation_registry": (cfg.criteria.generation_registry, generation_registry),
        "stable_cycle": (cfg.criteria.stable_cycle, stable_cycle),
        "intrinsic_goals": (cfg.criteria.intrinsic_goals, intrinsic_goals),
        "reproduction_capability": (
            cfg.criteria.reproduction_capability,
            reproduction_capability,
        ),
        "narrative_continuity": (
            cfg.criteria.narrative_continuity,
            narrative_continuity,
        ),
    }
    enabled = [
        (name, value) for name, (required, value) in criteria.items() if required
    ]
    weighted_criteria = cfg.weighted_score.criteria
    score = sum(
        weighted_criteria[name].points
        for name, (_, value) in criteria.items()
        if value and name in weighted_criteria
    )
    total_points = cfg.weighted_score.total_points

    def _score_threshold(value: float) -> float:
        return value * total_points if 0.0 <= value <= 1.0 else value

    alive_minimum_score = _score_threshold(cfg.thresholds.alive_minimum_score)
    fragile_minimum_score = _score_threshold(cfg.thresholds.fragile_minimum_score)
    required_for_alive = [
        name
        for name, (configured, _) in criteria.items()
        if configured
        and weighted_criteria.get(name) is not None
        and weighted_criteria[name].required_for_alive
    ]
    required_for_alive_present = all(criteria[name][1] for name in required_for_alive)
    if vital_state == "extinct":
        score = min(score, 20.0)
        status = LifeStatus.EXTINCT
    elif vital_state == "terminal":
        score = min(score, 40.0)
        status = LifeStatus.DYING
    elif not persistent_identity and not run_rows:
        status = LifeStatus.NOT_ALIVE_YET
    elif score >= alive_minimum_score and required_for_alive_present:
        status = LifeStatus.ALIVE
    elif score >= fragile_minimum_score:
        status = LifeStatus.FRAGILE
    else:
        status = LifeStatus.NOT_ALIVE_YET

    positives = [name for name, value in enabled if value]
    negatives = [name for name, value in enabled if not value]
    explanation = f"Statut {status.value}: {len(positives)}/{len(enabled)} sous-signaux configurés sont établis, score {score:g}/{total_points:g}."
    if negatives:
        explanation += " Manquants ou insuffisants: " + ", ".join(negatives) + "."
    if terminal:
        explanation += (
            f" Vital: état {vital_state}, risque {vital_timeline.get('risk_level')}."
        )
        causes = vital_timeline.get("causes")
        if isinstance(causes, list) and causes:
            explanation += " Causes: " + ", ".join(str(cause) for cause in causes) + "."

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
        "reproduction_capability": criteria["reproduction_capability"][1],
        "reproduction_eligible": reproduction_eligible,
        "narrative_continuity": narrative_continuity,
        "narrative_age_days": age_days,
        "terminal": terminal,
        "extinction": status is LifeStatus.EXTINCT,
        "vital_state": vital_state,
        "vital_risk_level": vital_timeline.get("risk_level"),
        "structured": {
            "identity": identity_signal,
            "narrative_continuity": narrative_continuity_signal,
            "goals": goal_signal,
            "generation": generation_signal,
            "extinction": extinction_signal,
            "stable_cycle": _signal(
                stable_cycle,
                1.0 if stable_cycle else 0.0,
                (
                    "required orchestrator cycles observed in order"
                    if stable_cycle
                    else "required orchestrator cycles are incomplete, anomalous or dominated by terminal events"
                ),
                cycle_evidence,
            ),
        },
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
        "extinction_events_count": extinction_events_count,
        "confirmed_extinction_events_count": confirmed_extinction_events_count,
        "reproduction_events_count": len(reproduction_events),
        "reproduction_capability": {
            "ok": reproduction_capability,
            "vital_age": vital_timeline.get("age"),
            "vital_state": vital_state,
            "vital_thresholds": vital_timeline.get("thresholds"),
            "reproduction_eligible": reproduction_eligible,
            "reproduction_events_count": len(reproduction_events),
            "descendants": detected_descendants,
        },
        "stable_cycle": cycle_evidence,
        "vital_timeline": vital_timeline,
        "thresholds": {
            "minimum_narrative_trajectory_days": cfg.thresholds.minimum_narrative_trajectory_days,
            "minimum_observed_cycles": cfg.thresholds.minimum_observed_cycles,
            "maximum_cycle_anomalies": cfg.thresholds.maximum_cycle_anomalies,
            "alive_minimum_score": cfg.thresholds.alive_minimum_score,
            "fragile_minimum_score": cfg.thresholds.fragile_minimum_score,
            "dying_degradation_minimum_score": cfg.thresholds.dying_degradation_minimum_score,
        },
        "weighted_score": {
            "total_points": total_points,
            "criteria": {
                name: {
                    "points": criterion.points,
                    "required_for_alive": criterion.required_for_alive,
                }
                for name, criterion in weighted_criteria.items()
            },
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
