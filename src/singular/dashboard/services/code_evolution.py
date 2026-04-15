from __future__ import annotations

from collections import Counter
from typing import Callable


def _as_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _normalize_target(record: dict[str, object]) -> str:
    file_value = record.get("file")
    if isinstance(file_value, str) and file_value.strip():
        return file_value.strip()
    module_value = record.get("module")
    if isinstance(module_value, str) and module_value.strip():
        return module_value.strip()
    skill_value = record.get("skill")
    if isinstance(skill_value, str) and skill_value.strip():
        if ":" in skill_value:
            _, path = skill_value.split(":", 1)
            if path.strip():
                return path.strip()
        return skill_value.strip()
    return "unknown"


def _normalize_change_type(record: dict[str, object]) -> str:
    for key in ("change_type", "change_category", "type"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    operator = record.get("operator")
    if not isinstance(operator, str) or not operator.strip():
        operator = record.get("op")
    if isinstance(operator, str) and operator.strip():
        return operator.strip().lower()
    return "unknown"


def _normalize_status(record: dict[str, object]) -> str:
    event = record.get("event")
    if isinstance(event, str):
        lowered = event.strip().lower()
        if lowered == "rollback":
            return "rollback"
        if lowered == "rejected":
            return "rejeté"
        if lowered == "accepted":
            return "accepté"

    accepted = _as_bool(record.get("accepted"))
    if accepted is None:
        accepted = _as_bool(record.get("ok"))
    if accepted is True:
        return "accepté"
    if accepted is False:
        return "rejeté"
    return "unknown"


def aggregate_code_evolution(
    records: list[dict[str, object]],
    *,
    life: str,
    record_life: Callable[[dict[str, object]], str],
    record_run_id: Callable[[dict[str, object]], str],
    as_float: Callable[[object], float | None],
) -> dict[str, object]:
    items: list[dict[str, object]] = []
    by_status: Counter[str] = Counter()
    by_change_type: Counter[str] = Counter()
    by_target: Counter[str] = Counter()

    for record in records:
        if record_life(record) != life:
            continue

        score_before = as_float(record.get("score_base"))
        score_after = as_float(record.get("score_new"))
        latency_before = as_float(record.get("ms_base"))
        latency_after = as_float(record.get("ms_new"))

        health = record.get("health")
        stability_after = None
        if isinstance(health, dict):
            stability_after = as_float(health.get("sandbox_stability"))
        stability_before = as_float(record.get("stability_base"))
        if stability_after is None:
            stability_after = as_float(record.get("stability_new"))

        change_type = _normalize_change_type(record)
        target = _normalize_target(record)
        status = _normalize_status(record)

        by_status[status] += 1
        by_change_type[change_type] += 1
        by_target[target] += 1

        items.append(
            {
                "target": target,
                "change_type": change_type,
                "metrics": {
                    "score": {"before": score_before, "after": score_after},
                    "latency_ms": {"before": latency_before, "after": latency_after},
                    "stability": {"before": stability_before, "after": stability_after},
                },
                "status": status,
                "timestamp": record.get("ts") if isinstance(record.get("ts"), str) else None,
                "run_id": record_run_id(record),
                "trace_id": (
                    record.get("trace_id") if isinstance(record.get("trace_id"), str) else None
                ),
            }
        )

    items.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)

    return {
        "life": life,
        "count": len(items),
        "items": items,
        "summary": {
            "by_status": dict(by_status),
            "by_change_type": dict(by_change_type),
            "by_target": dict(by_target),
        },
    }
