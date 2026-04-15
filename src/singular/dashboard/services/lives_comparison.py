from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable


_RECENT_ACTIVITY_EVENTS = {
    "mutation",
    "interaction",
    "consciousness",
    "quest",
    "quest_triggered",
    "quest_resolved",
    "decision",
    "action",
    "perception",
}
_PERCEPTION_EVENTS = {"perception", "signal", "sense", "observe"}
_DECISION_EVENTS = {"decision", "consciousness", "plan", "evaluate"}
_ACTION_EVENTS = {"action", "mutation", "interaction", "act", "execute"}
_INTERACTION_EVENTS = {"interaction", "conversation", "talk", "message"}
_OBJECTIVE_EVENTS = {"quest", "quest_triggered", "objective", "goal"}
_PROGRESS_EVENTS = {"quest_resolved", "objective_progress", "objective_completed", "goal_progress"}


def parse_ts(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def resolve_time_window_cutoff(time_window: str) -> datetime | None:
    normalized = time_window.strip().lower()
    now = datetime.now(timezone.utc)
    if normalized == "24h":
        return now - timedelta(hours=24)
    if normalized == "7d":
        return now - timedelta(days=7)
    if normalized == "30d":
        return now - timedelta(days=30)
    return None


def life_trend_label(points: list[float]) -> str:
    if len(points) < 2:
        return "plateau"
    window = points[-5:]
    first = window[0]
    last = window[-1]
    if last > first + 1.0:
        return "amélioration"
    if last < first - 1.0:
        return "dégradation"
    return "plateau"


def life_trend_rank(trend: str) -> int:
    if trend == "dégradation":
        return 0
    if trend == "plateau":
        return 1
    if trend == "amélioration":
        return 2
    return -1


def _normalized_event(record: dict[str, object]) -> str:
    event = record.get("event")
    if isinstance(event, str):
        return event.strip().lower()
    return ""


def compute_liveness_index(
    records: list[dict[str, object]],
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    reference = now or datetime.now(timezone.utc)
    sorted_records = sorted(records, key=lambda rec: str(rec.get("ts", "")))
    recent_cutoff = reference - timedelta(hours=24)
    loop_cutoff = reference - timedelta(hours=48)
    interaction_cutoff = reference - timedelta(days=7)

    component_details: dict[str, dict[str, object]] = {
        "recent_activity": {"score": 0.0, "count": 0, "cutoff": recent_cutoff.isoformat()},
        "perception_decision_action_loop": {"score": 0.0, "completed": False, "window_hours": 48},
        "active_objectives_progress": {"score": 0.0, "active_objectives": 0, "progress_events": 0},
        "interactions": {"score": 0.0, "count": 0, "window_days": 7},
        "validated_internal_modifications": {"score": 0.0, "accepted_useful_changes": 0},
    }
    proofs: list[dict[str, object]] = []

    # 1) Recent concrete activity
    recent_activity_count = 0
    for record in sorted_records:
        ts = parse_ts(record.get("ts"))
        if ts is None or ts < recent_cutoff:
            continue
        event_name = _normalized_event(record)
        has_concrete_mutation = any(
            key in record for key in ("score_base", "score_new", "accepted", "ok", "operator", "op")
        )
        if event_name in _RECENT_ACTIVITY_EVENTS or has_concrete_mutation:
            recent_activity_count += 1
            proofs.append(
                {
                    "ts": record.get("ts"),
                    "component": "recent_activity",
                    "evidence": "activité concrète récente",
                    "event": event_name or "mutation",
                }
            )
    if recent_activity_count >= 2:
        component_details["recent_activity"]["score"] = 1.0
    elif recent_activity_count == 1:
        component_details["recent_activity"]["score"] = 0.5
    component_details["recent_activity"]["count"] = recent_activity_count

    # 2) Perception → decision → action loop
    perception_ts: datetime | None = None
    decision_ts: datetime | None = None
    action_ts: datetime | None = None
    for record in sorted_records:
        ts = parse_ts(record.get("ts"))
        if ts is None or ts < loop_cutoff:
            continue
        event_name = _normalized_event(record)
        if perception_ts is None and (
            event_name in _PERCEPTION_EVENTS or isinstance(record.get("perception_summary"), str)
        ):
            perception_ts = ts
            proofs.append(
                {
                    "ts": record.get("ts"),
                    "component": "perception_decision_action_loop",
                    "evidence": "perception observée",
                    "event": event_name or "perception",
                }
            )
            continue
        if perception_ts is not None and decision_ts is None and ts >= perception_ts and (
            event_name in _DECISION_EVENTS
            or isinstance(record.get("decision_reason"), str)
            or isinstance(record.get("justification"), str)
        ):
            decision_ts = ts
            proofs.append(
                {
                    "ts": record.get("ts"),
                    "component": "perception_decision_action_loop",
                    "evidence": "décision observée",
                    "event": event_name or "decision",
                }
            )
            continue
        if perception_ts is not None and decision_ts is not None and ts >= decision_ts:
            accepted = record.get("accepted")
            if not isinstance(accepted, bool):
                accepted = record.get("ok")
            if event_name in _ACTION_EVENTS or isinstance(accepted, bool):
                action_ts = ts
                proofs.append(
                    {
                        "ts": record.get("ts"),
                        "component": "perception_decision_action_loop",
                        "evidence": "action observée",
                        "event": event_name or "action",
                    }
                )
                break
    loop_completed = perception_ts is not None and decision_ts is not None and action_ts is not None
    component_details["perception_decision_action_loop"]["completed"] = loop_completed
    component_details["perception_decision_action_loop"]["score"] = 1.0 if loop_completed else 0.0

    # 3) Active objectives with progress
    active_objectives_count = 0
    objective_progress_count = 0
    for record in sorted_records:
        event_name = _normalized_event(record)
        objective_value = record.get("objective")
        has_objective_payload = (
            event_name in _OBJECTIVE_EVENTS
            or isinstance(objective_value, str)
            or isinstance(record.get("objective_priorities"), dict)
        )
        if has_objective_payload:
            active_objectives_count += 1
        explicit_progress = event_name in _PROGRESS_EVENTS
        status = record.get("status")
        if not explicit_progress and isinstance(status, str):
            explicit_progress = status.strip().lower() in {"in_progress", "progress", "done", "completed", "success"}
        progress_value = record.get("progress")
        if not explicit_progress and isinstance(progress_value, (int, float)):
            explicit_progress = float(progress_value) > 0
        if explicit_progress and has_objective_payload:
            objective_progress_count += 1
            proofs.append(
                {
                    "ts": record.get("ts"),
                    "component": "active_objectives_progress",
                    "evidence": "objectif actif avec progression",
                    "event": event_name or "objective_progress",
                }
            )
    if active_objectives_count > 0 and objective_progress_count > 0:
        component_details["active_objectives_progress"]["score"] = 1.0
    component_details["active_objectives_progress"]["active_objectives"] = active_objectives_count
    component_details["active_objectives_progress"]["progress_events"] = objective_progress_count

    # 4) Interactions
    interaction_count = 0
    for record in sorted_records:
        ts = parse_ts(record.get("ts"))
        if ts is None or ts < interaction_cutoff:
            continue
        event_name = _normalized_event(record)
        interaction_payload = record.get("interaction")
        has_interaction = (
            event_name in _INTERACTION_EVENTS
            or isinstance(interaction_payload, dict)
            or isinstance(record.get("speaker"), str)
            or isinstance(record.get("user_message"), str)
            or isinstance(record.get("world_event"), str)
        )
        if has_interaction:
            interaction_count += 1
            proofs.append(
                {
                    "ts": record.get("ts"),
                    "component": "interactions",
                    "evidence": "interaction détectée",
                    "event": event_name or "interaction",
                }
            )
    if interaction_count >= 2:
        component_details["interactions"]["score"] = 1.0
    elif interaction_count == 1:
        component_details["interactions"]["score"] = 0.5
    component_details["interactions"]["count"] = interaction_count

    # 5) Useful validated internal modifications
    accepted_useful_modifications = 0
    for record in sorted_records:
        accepted = record.get("accepted")
        if not isinstance(accepted, bool):
            accepted = record.get("ok")
        if accepted is not True:
            continue
        score_base = record.get("score_base")
        score_new = record.get("score_new")
        score_improved = (
            isinstance(score_base, (int, float))
            and isinstance(score_new, (int, float))
            and float(score_new) < float(score_base)
        )
        health = record.get("health")
        health_score = health.get("score") if isinstance(health, dict) else None
        has_quality_signal = score_improved or isinstance(health_score, (int, float))
        if not has_quality_signal:
            continue
        accepted_useful_modifications += 1
        proofs.append(
            {
                "ts": record.get("ts"),
                "component": "validated_internal_modifications",
                "evidence": "modification interne validée utile",
                "event": _normalized_event(record) or "mutation",
            }
        )
    component_details["validated_internal_modifications"]["accepted_useful_changes"] = (
        accepted_useful_modifications
    )
    if accepted_useful_modifications >= 1:
        component_details["validated_internal_modifications"]["score"] = 1.0

    component_scores = [
        float(component_details[name]["score"])
        for name in (
            "recent_activity",
            "perception_decision_action_loop",
            "active_objectives_progress",
            "interactions",
            "validated_internal_modifications",
        )
    ]
    index = round((sum(component_scores) / 5.0) * 100.0, 1)

    sorted_proofs = sorted(
        proofs,
        key=lambda item: parse_ts(item.get("ts")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return {
        "index": index,
        "components": component_details,
        "proofs": sorted_proofs[:5],
    }


def aggregate_lives(
    records: list[dict[str, object]],
    *,
    registry: dict[str, object],
    compare_lives: set[str] | None,
    time_window: str,
    record_life: Callable[[dict[str, object]], str],
    record_run_id: Callable[[dict[str, object]], str],
    is_mutation_record: Callable[[dict[str, object]], bool],
    as_float: Callable[[object], float | None],
    alerts_from_records: Callable[[list[dict[str, object]]], list[dict[str, object]]],
    compute_vital_timeline: Callable[..., dict[str, object]],
    set_life_status: Callable[[str, str], object],
    registry_life_meta: Callable[[str, dict[str, object]], tuple[str | None, dict[str, object] | None]],
) -> tuple[dict[str, dict[str, object]], dict[str, object]]:
    active_life = registry.get("active")
    registry_lives = registry.get("lives")
    if not isinstance(registry_lives, dict):
        registry_lives = {}
    cutoff = resolve_time_window_cutoff(time_window)
    by_life: dict[str, list[dict[str, object]]] = {}
    unattached_runs: dict[str, int] = {}
    for record in records:
        if cutoff is not None:
            ts = parse_ts(record.get("ts"))
            if ts is None or ts < cutoff:
                continue
        life_name = record_life(record)
        if compare_lives and life_name != "unknown" and life_name not in compare_lives:
            continue
        if life_name == "unknown":
            run_id = record_run_id(record)
            unattached_runs[run_id] = unattached_runs.get(run_id, 0) + 1
            continue
        by_life.setdefault(life_name, []).append(record)

    comparison: dict[str, dict[str, object]] = {}
    for slug, raw_meta in registry_lives.items():
        if not isinstance(slug, str):
            continue
        registry_status = "active"
        display_name = slug
        if isinstance(raw_meta, dict):
            status_value = raw_meta.get("status")
            if isinstance(status_value, str) and status_value in {"active", "extinct"}:
                registry_status = status_value
            name_value = raw_meta.get("name")
            if isinstance(name_value, str) and name_value:
                display_name = name_value
        else:
            status_value = getattr(raw_meta, "status", None)
            if isinstance(status_value, str) and status_value in {"active", "extinct"}:
                registry_status = status_value
            name_value = getattr(raw_meta, "name", None)
            if isinstance(name_value, str) and name_value:
                display_name = name_value
        is_selected = isinstance(active_life, str) and active_life in {slug, display_name}
        is_extinct = registry_status == "extinct"
        comparison[display_name] = {
            "health_score": None,
            "progression_slope": None,
            "failure_rate": None,
            "evolution_speed": None,
            "mutations": 0,
            "current_health_score": None,
            "trend": "plateau",
            "trend_rank": life_trend_rank("plateau"),
            "stability": None,
            "last_activity": None,
            "alerts": [],
            "alerts_count": 0,
            "iterations": 0,
            "selected_life": is_selected,
            "life_status": registry_status,
            "is_registry_active_life": registry_status == "active",
            "has_recent_activity": False,
            "extinction_seen_in_runs": is_extinct,
            "run_terminated": False,
            "vital_timeline": compute_vital_timeline(
                age=0,
                current_health=None,
                failure_rate=None,
                failure_streak=0,
                extinction_seen=is_extinct,
                registry_status=registry_status,
            ),
            "life_liveness_index": 0.0,
            "life_liveness_components": {
                "recent_activity": {"score": 0.0, "count": 0},
                "perception_decision_action_loop": {"score": 0.0, "completed": False},
                "active_objectives_progress": {
                    "score": 0.0,
                    "active_objectives": 0,
                    "progress_events": 0,
                },
                "interactions": {"score": 0.0, "count": 0},
                "validated_internal_modifications": {
                    "score": 0.0,
                    "accepted_useful_changes": 0,
                },
            },
            "life_liveness_proofs": [],
        }

    for life_name, all_records in by_life.items():
        all_records = sorted(all_records, key=lambda rec: str(rec.get("ts", "")))
        mutation_records = [rec for rec in all_records if is_mutation_record(rec)]

        score_points = [
            (
                as_float(rec.get("score_base")),
                as_float(rec.get("score_new")),
            )
            for rec in mutation_records
        ]
        health_values: list[float] = []
        health_score_points: list[float] = []
        sandbox_stability_points: list[float] = []
        for rec in mutation_records:
            health = rec.get("health")
            if isinstance(health, dict):
                score = as_float(health.get("score"))
                if score is not None:
                    health_values.append(score)
                    health_score_points.append(score)
                stability = as_float(health.get("sandbox_stability"))
                if stability is not None:
                    sandbox_stability_points.append(stability)

        ms_points = [as_float(rec.get("ms_new")) for rec in mutation_records]
        ms_points = [value for value in ms_points if value is not None]
        accepted_values: list[bool] = []
        for rec in mutation_records:
            accepted = rec.get("accepted")
            if not isinstance(accepted, bool):
                accepted = rec.get("ok")
            if isinstance(accepted, bool):
                accepted_values.append(accepted)

        first_base = next((base for base, _ in score_points if base is not None), None)
        last_new = next(
            (new for _, new in reversed(score_points) if new is not None), None
        )
        progression_slope = None
        if first_base is not None and last_new is not None and len(mutation_records) > 1:
            progression_slope = (first_base - last_new) / (len(mutation_records) - 1)

        failure_rate = None
        if accepted_values:
            failures = sum(1 for value in accepted_values if not value)
            failure_rate = failures / len(accepted_values)

        evolution_speed = None
        if ms_points:
            evolution_speed = sum(ms_points) / len(ms_points)

        last_timestamp = next(
            (str(rec.get("ts")) for rec in reversed(all_records) if isinstance(rec.get("ts"), str)),
            None,
        )
        last_event = next(
            (
                str(rec.get("event"))
                for rec in reversed(all_records)
                if isinstance(rec.get("event"), str)
            ),
            None,
        )
        extinction_seen = any(rec.get("event") == "death" for rec in all_records)
        run_terminated = last_event == "death"
        slug, raw_meta = registry_life_meta(life_name, registry_lives)
        registry_status = "active"
        if isinstance(raw_meta, dict):
            status_value = raw_meta.get("status")
            if isinstance(status_value, str) and status_value in {"active", "extinct"}:
                registry_status = status_value
        elif slug is not None:
            registry_meta = registry_lives.get(slug)
            status_value = getattr(registry_meta, "status", None)
            if isinstance(status_value, str) and status_value in {"active", "extinct"}:
                registry_status = status_value
        if extinction_seen and slug is not None and registry_status != "extinct":
            set_life_status(slug, "extinct")
            registry_status = "extinct"
        is_selected = isinstance(active_life, str) and active_life in {life_name, slug}
        trend = life_trend_label(health_score_points)
        alerts = alerts_from_records(mutation_records) if mutation_records else []
        current_health_score = health_score_points[-1] if health_score_points else None
        stability_score = (
            sum(sandbox_stability_points) / len(sandbox_stability_points)
            if sandbox_stability_points
            else None
        )
        liveness = compute_liveness_index(all_records)

        comparison[life_name] = {
            "health_score": (
                sum(health_values) / len(health_values) if health_values else None
            ),
            "progression_slope": progression_slope,
            "failure_rate": failure_rate,
            "evolution_speed": evolution_speed,
            "mutations": len(mutation_records),
            "current_health_score": current_health_score,
            "trend": trend,
            "trend_rank": life_trend_rank(trend),
            "stability": stability_score,
            "last_activity": last_timestamp,
            "alerts": alerts,
            "alerts_count": len(alerts),
            "iterations": len(mutation_records),
            "selected_life": is_selected,
            "life_status": registry_status,
            "is_registry_active_life": registry_status == "active",
            "has_recent_activity": last_timestamp is not None,
            "extinction_seen_in_runs": extinction_seen,
            "run_terminated": run_terminated,
            "vital_timeline": compute_vital_timeline(
                age=len(mutation_records),
                current_health=current_health_score,
                failure_rate=failure_rate,
                failure_streak=0,
                extinction_seen=extinction_seen,
                registry_status=registry_status,
            ),
            "life_liveness_index": liveness["index"],
            "life_liveness_components": liveness["components"],
            "life_liveness_proofs": liveness["proofs"],
        }
    unattached_summary = {
        "records_count": sum(unattached_runs.values()),
        "runs_count": len(unattached_runs),
        "runs": [
            {"run_id": run_id, "records_count": count}
            for run_id, count in sorted(unattached_runs.items())
        ],
    }
    return comparison, unattached_summary
