from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable


def parse_ts(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


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
