from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _extract_skill_name(record: dict[str, Any]) -> str | None:
    for key in ("skill", "skill_name", "operator", "op", "action"):
        value = record.get(key)
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return normalized
    return None


def _extract_task_label(record: dict[str, Any]) -> str | None:
    for key in ("task", "objective", "prompt", "event"):
        value = record.get(key)
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return normalized if len(normalized) <= 80 else f"{normalized[:77]}..."
    return None


def build_daily_skills_snapshot(
    records: list[dict[str, Any]], *, now: datetime | None = None
) -> dict[str, Any]:
    now_dt = now.astimezone(timezone.utc) if now is not None else datetime.now(timezone.utc)
    since_24h = now_dt - timedelta(hours=24)
    since_7d = now_dt - timedelta(days=7)
    previous_24h = since_24h - timedelta(hours=24)
    per_skill: dict[str, dict[str, Any]] = {}
    total_24h = 0
    total_7d = 0

    for record in records:
        skill_name = _extract_skill_name(record)
        if skill_name is None:
            continue
        timestamp = _parse_timestamp(record.get("ts"))
        accepted = record.get("accepted")
        if not isinstance(accepted, bool):
            accepted = record.get("ok")
        skill_entry = per_skill.setdefault(
            skill_name,
            {
                "skill": skill_name,
                "total_uses": 0,
                "uses_24h": 0,
                "uses_7d": 0,
                "uses_previous_24h": 0,
                "success_total": 0,
                "success_24h": 0,
                "attempts_with_result": 0,
                "last_used_at": None,
                "first_seen_at": None,
                "associated_tasks": [],
            },
        )
        skill_entry["total_uses"] += 1
        if timestamp is not None:
            if skill_entry["first_seen_at"] is None or timestamp < skill_entry["first_seen_at"]:
                skill_entry["first_seen_at"] = timestamp
            if skill_entry["last_used_at"] is None or timestamp > skill_entry["last_used_at"]:
                skill_entry["last_used_at"] = timestamp
            if timestamp >= since_24h:
                skill_entry["uses_24h"] += 1
                total_24h += 1
            if timestamp >= since_7d:
                skill_entry["uses_7d"] += 1
                total_7d += 1
            if previous_24h <= timestamp < since_24h:
                skill_entry["uses_previous_24h"] += 1
        task_label = _extract_task_label(record)
        if task_label and task_label not in skill_entry["associated_tasks"] and len(skill_entry["associated_tasks"]) < 4:
            skill_entry["associated_tasks"].append(task_label)
        if isinstance(accepted, bool):
            skill_entry["attempts_with_result"] += 1
            if accepted:
                skill_entry["success_total"] += 1
                if timestamp is not None and timestamp >= since_24h:
                    skill_entry["success_24h"] += 1

    top_skills: list[dict[str, Any]] = []
    learned = 0
    used = 0
    improved = 0
    for item in per_skill.values():
        attempts = item["attempts_with_result"]
        success_rate = item["success_total"] / attempts if attempts else None
        success_rate_24h = item["success_24h"] / item["uses_24h"] if item["uses_24h"] else None
        if item["uses_24h"] > item["uses_previous_24h"]:
            trend = "hausse"
        elif item["uses_24h"] < item["uses_previous_24h"]:
            trend = "baisse"
        else:
            trend = "stable"
        first_seen = item["first_seen_at"]
        if isinstance(first_seen, datetime) and first_seen >= since_7d:
            learned += 1
        if item["uses_24h"] > 0:
            used += 1
        if trend == "hausse" and success_rate_24h is not None and success_rate_24h >= 0.6:
            improved += 1
        top_skills.append(
            {
                "skill": item["skill"],
                "total_uses": item["total_uses"],
                "frequency": {"uses_24h": item["uses_24h"], "uses_7d": item["uses_7d"]},
                "success_rate": success_rate,
                "last_used_at": (
                    item["last_used_at"].isoformat() if isinstance(item["last_used_at"], datetime) else None
                ),
                "associated_tasks": item["associated_tasks"],
                "trend": trend,
            }
        )
    top_skills.sort(
        key=lambda entry: (
            int(entry["frequency"]["uses_24h"]),
            int(entry["frequency"]["uses_7d"]),
            int(entry["total_uses"]),
        ),
        reverse=True,
    )
    return {
        "top_skills": top_skills[:8],
        "frequency_totals": {"uses_24h": total_24h, "uses_7d": total_7d},
        "progression_pipeline": {
            "learned": learned,
            "used": used,
            "improved": improved,
            "completion_rate": (improved / learned) if learned else None,
        },
    }
