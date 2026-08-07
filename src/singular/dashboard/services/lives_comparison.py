from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable
from urllib.parse import quote


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

_SERIES_METRICS = (
    "health", "energy", "mood", "autonomy", "liveliness", "objectives",
    "interactions", "accepted_mutations", "failures",
)

_LIVENESS_FORMULA_VERSION = "liveness-v1.0"


def _data_freshness(records: list[dict[str, object]], reference: datetime) -> dict[str, object]:
    timestamps = [parsed for record in records if (parsed := parse_ts(record.get("ts"))) is not None]
    if not timestamps:
        return {"last_observation_at": None, "age_seconds": None, "status": "missing"}
    latest = max(timestamps)
    age_seconds = max(0, int((reference - latest).total_seconds()))
    status = "fresh" if age_seconds <= 86_400 else "stale" if age_seconds <= 604_800 else "expired"
    return {"last_observation_at": latest.isoformat(), "age_seconds": age_seconds, "status": status}


def _component_recommendations(components: dict[str, dict[str, object]]) -> list[str]:
    """Return actions tied to an observed deficient component, never generic alerts."""
    recommendations: list[str] = []
    if float(components["interactions"]["score"]) == 0.0:
        recommendations.append("Initier un échange ciblé : aucune interaction observée depuis 7 jours.")
    if float(components["recent_activity"]["score"]) == 0.0:
        recommendations.append("Planifier une action concrète : aucune activité qualifiante observée depuis 24 h.")
    if not components["perception_decision_action_loop"]["completed"]:
        recommendations.append("Exécuter une boucle perception → décision → action : aucune boucle complète observée sur 48 h.")
    objectives = components["active_objectives_progress"]
    if int(objectives["active_objectives"]) > 0 and int(objectives["progress_events"]) == 0:
        recommendations.append("Faire progresser un objectif actif : aucun événement de progression n'est observé.")
    return recommendations


def build_life_timeseries(
    records: list[dict[str, object]], *, life: str, time_window: str = "24h",
    resolution: str = "hour", limit: int = 500, mutation_index: int | None = None,
    record_run_id: Callable[[dict[str, object]], str] = lambda _: "unknown",
) -> dict[str, object]:
    """Build a bounded, bucketed chronology while retaining source evidence links."""
    windows = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30), "all": None}
    resolutions = {"raw": None, "hour": timedelta(hours=1), "day": timedelta(days=1)}
    if time_window not in windows:
        raise ValueError("time_window must be one of: 24h, 7d, 30d, all")
    if resolution not in resolutions:
        raise ValueError("resolution must be one of: raw, hour, day")
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")

    dated = [(ts, rec) for rec in records if (ts := parse_ts(rec.get("ts"))) is not None]
    dated.sort(key=lambda item: item[0])
    mutation_rows = [(ts, rec) for ts, rec in dated if any(k in rec for k in ("accepted", "ok", "score_base", "score_new", "operator", "op"))]
    mutation_indexes = {id(rec): index for index, (_, rec) in enumerate(mutation_rows)}
    pivot = None
    if mutation_index is not None:
        if mutation_index < 0 or mutation_index >= len(mutation_rows):
            raise IndexError("mutation_index out of range")
        pivot = mutation_rows[mutation_index][0]
    end = dated[-1][0] if dated else datetime.now(timezone.utc)
    cutoff = end - windows[time_window] if windows[time_window] is not None else None
    dated = [(ts, rec) for ts, rec in dated if cutoff is None or ts >= cutoff]

    def number(rec: dict[str, object], *names: str) -> float | None:
        for name in names:
            value: object = rec.get(name)
            if name == "health" and isinstance(value, dict):
                value = value.get("score")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
        return None

    buckets: dict[str, dict[str, object]] = {}
    step = resolutions[resolution]
    for ts, rec in dated:
        bucket_ts = ts
        if step == timedelta(hours=1):
            bucket_ts = ts.replace(minute=0, second=0, microsecond=0)
        elif step == timedelta(days=1):
            bucket_ts = ts.replace(hour=0, minute=0, second=0, microsecond=0)
        key = (bucket_ts.isoformat() if step else ts.isoformat())
        bucket = buckets.setdefault(key, {"timestamp": key, "values": {metric: [] for metric in _SERIES_METRICS}, "events": [], "proofs": []})
        values = bucket["values"]
        assert isinstance(values, dict)
        event = _normalized_event(rec)
        accepted = rec.get("accepted") if isinstance(rec.get("accepted"), bool) else rec.get("ok")
        samples = {
            "health": number(rec, "health", "health_score"), "energy": number(rec, "energy"),
            "mood": number(rec, "mood", "humeur"), "autonomy": number(rec, "autonomy", "autonomy_index"),
            "liveliness": number(rec, "liveliness", "liveness", "vivacity"),
            "objectives": number(rec, "objectives", "objectives_count"),
            "interactions": 1.0 if event in _INTERACTION_EVENTS else None,
            "accepted_mutations": 1.0 if accepted is True else None,
            "failures": 1.0 if accepted is False or event in {"failure", "error", "mutation_failed"} else None,
        }
        for metric, value in samples.items():
            if value is not None:
                values[metric].append(value)
        run_id = record_run_id(rec)
        proof = {"timestamp": ts.isoformat(), "event": event or "observation", "run_id": run_id,
                 "href": f"/api/runs/{quote(run_id, safe='')}/timeline?page=1&page_size=120"}
        bucket["proofs"].append(proof)
        notable = event in (_OBJECTIVE_EVENTS | _PROGRESS_EVENTS | _INTERACTION_EVENTS | {"mutation", "death", "birth", "skill_acquired", "skill_lost"})
        if notable or any(key in rec for key in ("objective", "skill", "accepted", "ok")):
            bucket["events"].append({**proof, "objective": rec.get("objective"), "skill": rec.get("skill"), "accepted": accepted,
                                     "mutation_index": mutation_indexes.get(id(rec))})

    points = list(buckets.values())[-limit:]
    for point in points:
        values = point["values"]
        for metric, samples in values.items():
            values[metric] = (round(sum(samples) / len(samples), 3) if samples and metric not in {"interactions", "accepted_mutations", "failures"} else sum(samples)) if samples else None
    comparison = None
    if pivot is not None:
        before = [p for p in points if parse_ts(p["timestamp"]) < pivot]
        after = [p for p in points if parse_ts(p["timestamp"]) >= pivot]
        comparison = {"mutation_index": mutation_index, "pivot": pivot.isoformat(), "before": _series_averages(before), "after": _series_averages(after)}
    return {"life": life, "window": time_window, "resolution": resolution, "limit": limit,
            "count": len(points), "truncated": len(buckets) > limit, "metrics": list(_SERIES_METRICS),
            "points": points, "mutation_comparison": comparison}


def _series_averages(points: list[dict[str, object]]) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    for metric in _SERIES_METRICS:
        values = [p["values"][metric] for p in points if p["values"].get(metric) is not None]
        result[metric] = round(sum(values) / len(values), 3) if values else None
    return result


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


def normalize_life_status(value: object) -> str:
    if not isinstance(value, str):
        return "unknown"
    normalized = value.strip().lower()
    if normalized in {"active", "archived", "extinct", "dead", "stopped", "unknown"}:
        return normalized
    return "unknown"


def _status_is_dead(status: str) -> bool:
    return status in {"extinct", "dead"}


def _status_is_terminated(status: str) -> bool:
    return status in {"extinct", "dead", "stopped"}


def _normalized_event(record: dict[str, object]) -> str:
    event = record.get("event")
    if isinstance(event, str):
        return event.strip().lower()
    return ""


def _is_voluntary_budget_record(record: dict[str, object]) -> bool:
    return record.get("voluntary_budget") is True or _normalized_event(record) in {
        "loop.budget_exhausted",
        "daemon.budget_exhausted",
    }


def compute_mutation_viability(records: list[dict[str, object]]) -> dict[str, object]:
    mutation_records = [
        record for record in records
        if any(key in record for key in ("score_base", "score_new", "accepted", "ok", "operator", "op"))
    ]
    decided = []
    useful = 0
    failures = 0
    for record in mutation_records:
        accepted = record.get("accepted")
        if not isinstance(accepted, bool):
            accepted = record.get("ok")
        if isinstance(accepted, bool):
            decided.append(accepted)
            if not accepted:
                failures += 1
        score_base = record.get("score_base")
        score_new = record.get("score_new")
        improved = (
            isinstance(score_base, (int, float))
            and isinstance(score_new, (int, float))
            and float(score_new) < float(score_base)
        )
        health = record.get("health")
        has_health = isinstance(health, dict) and isinstance(health.get("score"), (int, float))
        if accepted is True and (improved or has_health):
            useful += 1
    score = None
    if mutation_records:
        acceptance = sum(1 for value in decided if value) / len(decided) if decided else 0.0
        usefulness = useful / len(mutation_records)
        failure_penalty = failures / len(mutation_records)
        score = round(max(0.0, min(1.0, (acceptance * 0.5) + (usefulness * 0.5) - (failure_penalty * 0.25))) * 100.0, 1)
    return {
        "score": score,
        "mutation_count": len(mutation_records),
        "accepted_count": sum(1 for value in decided if value),
        "rejected_count": sum(1 for value in decided if not value),
        "accepted_useful_changes": useful,
    }


def compute_liveness_index(
    records: list[dict[str, object]],
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    reference = now or datetime.now(timezone.utc)
    sorted_records = sorted(records, key=lambda rec: str(rec.get("ts", "")))
    autonomy_records = [record for record in sorted_records if not _is_voluntary_budget_record(record)]
    budgeted_periods_ignored = len(sorted_records) - len(autonomy_records)
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
    if budgeted_periods_ignored:
        autonomy_payload = compute_liveness_index(autonomy_records, now=reference)
        autonomy_index = autonomy_payload["index"]
    else:
        autonomy_index = index
    mutation_viability = compute_mutation_viability(sorted_records)

    sorted_proofs = sorted(
        proofs,
        key=lambda item: parse_ts(item.get("ts")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    missing_data = [name for name, detail in component_details.items() if float(detail["score"]) == 0.0]
    freshness = _data_freshness(sorted_records, reference)
    observed_components = len(component_details) - len(missing_data)
    confidence = round(observed_components / len(component_details), 2)
    liveness_diagnostic = {
        "formula_version": _LIVENESS_FORMULA_VERSION,
        "formula": "100 × (activité + boucle PDA + objectifs/progrès + interactions + modifications validées) / 5",
        "unit": "points sur 100", "window": {"recent_activity_hours": 24, "pda_loop_hours": 48, "interactions_days": 7, "objectives": "historique disponible", "modifications": "historique disponible"},
        "components": component_details, "freshness": freshness,
        "confidence": {"level": "high" if confidence >= .8 else "medium" if confidence >= .4 else "low", "score": confidence, "basis": f"{observed_components}/5 composantes étayées"},
        "missing_data": missing_data, "proofs": sorted_proofs[:5], "recommendations": _component_recommendations(component_details),
    }
    autonomy_diagnostic = {**liveness_diagnostic, "formula_version": "autonomy-v1.0", "formula": "indice de vivacité recalculé après exclusion des arrêts volontaires de budget", "excluded_records": budgeted_periods_ignored}
    mutation_missing = [] if mutation_viability["mutation_count"] else ["mutations décidées", "changements utiles validés"]
    mutation_diagnostic = {
        "formula_version": "mutation-viability-v1.0", "formula": "100 × clamp(0, 1, 0,5 × acceptation + 0,5 × utilité − 0,25 × échecs)", "unit": "points sur 100", "window": "historique disponible",
        "components": mutation_viability, "freshness": freshness,
        "confidence": {"level": "high" if mutation_viability["mutation_count"] >= 10 else "medium" if mutation_viability["mutation_count"] >= 3 else "low", "sample_size": mutation_viability["mutation_count"]},
        "missing_data": mutation_missing, "proofs": [proof for proof in sorted_proofs if proof["component"] == "validated_internal_modifications"], "recommendations": [],
    }
    return {
        "index": index,
        "autonomy_index": autonomy_index,
        "budgeted_periods_ignored": budgeted_periods_ignored,
        "mutation_viability": mutation_viability,
        "components": component_details,
        "proofs": sorted_proofs[:5],
        "indices": {"liveness": liveness_diagnostic, "autonomy": autonomy_diagnostic, "mutation_viability": mutation_diagnostic},
        "recommendations": liveness_diagnostic["recommendations"],
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
            registry_status = normalize_life_status(raw_meta.get("status", "active"))
            name_value = raw_meta.get("name")
            if isinstance(name_value, str) and name_value:
                display_name = name_value
        else:
            registry_status = normalize_life_status(getattr(raw_meta, "status", "active"))
            name_value = getattr(raw_meta, "name", None)
            if isinstance(name_value, str) and name_value:
                display_name = name_value
        is_selected = isinstance(active_life, str) and active_life in {slug, display_name}
        is_extinct = _status_is_dead(registry_status)
        is_terminated = _status_is_terminated(registry_status)
        comparison[slug] = {
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
            "run_terminated": is_terminated,
            "registry_run_status_inconsistency": False,
            "status_reconciliation_suggestion": None,
            "vital_timeline": compute_vital_timeline(
                age=0,
                current_health=None,
                failure_rate=None,
                failure_streak=0,
                extinction_seen=is_extinct,
                registry_status=registry_status,
            ),
            "life_liveness_index": 0.0,
            "autonomy_index": 0.0,
            "mutation_viability": {"score": None, "mutation_count": 0, "accepted_count": 0, "rejected_count": 0, "accepted_useful_changes": 0},
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
            "score_diagnostics": {},
            "score_recommendations": [],
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
            registry_status = normalize_life_status(raw_meta.get("status", "active"))
        elif slug is not None:
            registry_meta = registry_lives.get(slug)
            registry_status = normalize_life_status(getattr(registry_meta, "status", "active"))
        if registry_status == "unknown" and life_name in comparison:
            registry_status = str(comparison[life_name].get("life_status", "unknown"))
        extinction_seen = extinction_seen or _status_is_dead(registry_status)
        run_terminated = run_terminated or _status_is_terminated(registry_status)
        registry_run_status_inconsistency = (
            extinction_seen and slug is not None and not _status_is_dead(registry_status)
        )
        status_reconciliation_suggestion = (
            "mark_extinct" if registry_run_status_inconsistency else None
        )
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
            "registry_run_status_inconsistency": registry_run_status_inconsistency,
            "status_reconciliation_suggestion": status_reconciliation_suggestion,
            "vital_timeline": compute_vital_timeline(
                age=len(mutation_records),
                current_health=current_health_score,
                failure_rate=failure_rate,
                failure_streak=0,
                extinction_seen=extinction_seen,
                registry_status=registry_status,
            ),
            "life_liveness_index": liveness["index"],
            "autonomy_index": liveness.get("autonomy_index", liveness["index"]),
            "mutation_viability": liveness.get("mutation_viability", compute_mutation_viability(all_records)),
            "life_liveness_components": liveness["components"],
            "life_liveness_proofs": liveness["proofs"],
            "score_diagnostics": {
                **liveness["indices"],
                "health": {"formula_version": "health-observation-v1.0", "formula": "dernière valeur health.score observée", "unit": "points sur 100", "window": time_window,
                    "components": {"latest": current_health_score, "observations": len(health_score_points)}, "freshness": _data_freshness(all_records, datetime.now(timezone.utc)),
                    "confidence": {"level": "high" if len(health_score_points) >= 5 else "medium" if len(health_score_points) >= 2 else "low", "sample_size": len(health_score_points)}, "missing_data": [] if health_score_points else ["health.score"], "proofs": [], "recommendations": [],
                    "change_reason": f"variation de {health_score_points[-1] - health_score_points[0]:+.1f} points sur {len(health_score_points)} observations" if len(health_score_points) >= 2 else "variation indéterminable : moins de deux observations"}},
            "score_recommendations": liveness["recommendations"],
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
