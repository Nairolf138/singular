from __future__ import annotations

import json
from pathlib import Path
from typing import Callable


def extract_objective_priorities(record: dict[str, object]) -> dict[str, float]:
    candidates = (
        record.get("objective_priorities"),
        record.get("objective_weights"),
        record.get("objectives"),
    )
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        parsed: dict[str, float] = {}
        for key, value in candidate.items():
            if not isinstance(key, str):
                continue
            if isinstance(value, (int, float)):
                parsed[key] = float(value)
            elif isinstance(value, dict):
                nested_priority = value.get("priority")
                if isinstance(nested_priority, (int, float)):
                    parsed[key] = float(nested_priority)
        if parsed:
            return parsed
    return {}


def build_trajectory(
    records: list[dict[str, object]],
    quests_path: Path,
    record_run_id: Callable[[dict[str, object]], str],
) -> dict[str, object]:
    active: list[dict[str, object]] = []
    paused: list[dict[str, object]] = []
    completed: list[dict[str, object]] = []
    if quests_path.exists():
        try:
            quests_data = json.loads(quests_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            quests_data = {}
        if isinstance(quests_data, dict):
            active = quests_data.get("active") if isinstance(quests_data.get("active"), list) else []
            paused = quests_data.get("paused") if isinstance(quests_data.get("paused"), list) else []
            completed = quests_data.get("completed") if isinstance(quests_data.get("completed"), list) else []

    objective_status: dict[str, str] = {}
    for item in active:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            objective_status[item["name"]] = "in_progress"
    for item in paused:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            objective_status[item["name"]] = "abandoned"
    for item in completed:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            objective_status[item["name"]] = "completed"

    previous: dict[str, float] = {}
    priority_changes: list[dict[str, object]] = []
    for record in records:
        priorities = extract_objective_priorities(record)
        if not priorities:
            continue
        ts = record.get("ts") if isinstance(record.get("ts"), str) else None
        for objective, new_value in priorities.items():
            old_value = previous.get(objective)
            if old_value is None:
                previous[objective] = new_value
                continue
            if abs(new_value - old_value) >= 0.01:
                priority_changes.append(
                    {
                        "objective": objective,
                        "at": ts,
                        "from": round(old_value, 4),
                        "to": round(new_value, 4),
                        "delta": round(new_value - old_value, 4),
                    }
                )
                previous[objective] = new_value

    links: list[dict[str, object]] = []
    major_events = {"death", "interaction", "quest", "quest_triggered", "quest_resolved", "consciousness"}
    for record in records:
        event = record.get("event")
        if not isinstance(event, str):
            continue
        if event not in major_events and not isinstance(record.get("self_narrative_event"), str):
            continue
        objective = record.get("objective")
        if not isinstance(objective, str):
            continue
        links.append(
            {
                "objective": objective,
                "event": record.get("self_narrative_event", event),
                "at": record.get("ts") if isinstance(record.get("ts"), str) else None,
                "run": record_run_id(record),
            }
        )

    # Correlation IDs are deliberately the primary join key: a breaker alert
    # can therefore lead to its sandbox cause, mutation and impacted path even
    # when these were emitted by different subsystems.
    correlated: dict[str, list[dict[str, object]]] = {}
    for record in records:
        correlation_id = record.get("correlation_id")
        if not isinstance(correlation_id, str) or not correlation_id:
            continue
        event = record.get("event") or record.get("event_type") or (
            "mutation" if any(key in record for key in ("op", "operator", "diff")) else "record"
        )
        item = {
            "correlation_id": correlation_id,
            "timestamp": record.get("ts", record.get("timestamp")),
            "event": event,
            "cause": record.get("initial_cause", record.get("category", record.get("source_error_type"))),
            "decision": record.get("decision_reason", record.get("reason", record.get("accepted"))),
            "consequence": record.get("human_summary", record.get("result", record.get("self_narrative_event"))),
            "life": record.get("life_id", record.get("life", record.get("organism"))),
            "corrective_action": record.get("corrective_action"),
            "mutation": record.get("operator", record.get("op")),
            "path": record.get("impacted_file", record.get("path")),
            "run": record_run_id(record),
        }
        correlated.setdefault(correlation_id, []).append(item)
    chronology = [item for group in correlated.values() for item in group]
    chronology.sort(key=lambda item: str(item.get("timestamp") or ""))

    return {
        "objectives": {
            "counts": {
                "in_progress": sum(1 for status in objective_status.values() if status == "in_progress"),
                "abandoned": sum(1 for status in objective_status.values() if status == "abandoned"),
                "completed": sum(1 for status in objective_status.values() if status == "completed"),
            },
            "in_progress": [name for name, status in objective_status.items() if status == "in_progress"],
            "abandoned": [name for name, status in objective_status.items() if status == "abandoned"],
            "completed": [name for name, status in objective_status.items() if status == "completed"],
        },
        "priority_changes": priority_changes[-40:],
        "objective_narrative_links": links[-40:],
        "causal_chronology": chronology[-100:],
        "correlations": {key: value for key, value in correlated.items()},
    }
