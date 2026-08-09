"""Stable metrics contract shared by dashboard endpoints.

Centralizes the life counter keys and labels rendered by ecosystem, cockpit, and
comparison views.
"""

from __future__ import annotations

from typing import Any


LIFE_METRIC_FIELDS = (
    "selected_life",
    "registry_status",
    "is_registry_active_life",
    "has_recent_activity",
    "life_status",
    "viability_status",
)


def _viability_status(payload: dict[str, Any]) -> str:
    """Return an explicit viability state without borrowing the vital state."""
    value = payload.get("viability_status")
    if value in {"viable", "non_viable", "unknown"}:
        return str(value)
    viability = payload.get("mutation_viability")
    score = viability.get("score") if isinstance(viability, dict) else None
    if not isinstance(score, (int, float)):
        return "unknown"
    return "viable" if score >= 50 else "non_viable"


def normalize_life_metrics(
    lives: dict[str, dict[str, Any]],
    *,
    selected_life_id: str | None,
    registry_active_life_id: str | None,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Apply the sole dashboard meaning of the six life identity/status fields.

    Selection is an operator concern, registry activity is the registry pointer,
    recent activity is event-derived, and vital and viability states remain
    independent.  Contradictions are returned instead of being reconciled.
    """
    normalized: dict[str, dict[str, Any]] = {}
    inconsistencies: list[dict[str, Any]] = []
    latest_life_id: str | None = None
    latest_timestamp: str | None = None
    for life_id, source in lives.items():
        row = dict(source)
        row["selected_life"] = life_id == selected_life_id
        row["is_registry_active_life"] = life_id == registry_active_life_id
        row["has_recent_activity"] = bool(row.get("last_activity"))
        row["viability_status"] = _viability_status(row)
        # Do not infer life_status from registry_status or viability_status.
        row["life_status"] = row.get("life_status")
        timestamp = row.get("last_activity")
        if isinstance(timestamp, str) and (latest_timestamp is None or timestamp > latest_timestamp):
            latest_timestamp, latest_life_id = timestamp, life_id
        if row.get("registry_run_status_inconsistency"):
            inconsistencies.append({
                "life_id": life_id,
                "kind": "registry_vital_status_conflict",
                "registry_status": row.get("registry_status"),
                "life_status": row.get("life_status"),
            })
        normalized[life_id] = row
    identities = {
        "selected_life_id": selected_life_id,
        "registry_active_life_id": registry_active_life_id,
        "latest_event_life_id": latest_life_id,
        "latest_event_at": latest_timestamp,
        "latest_event_life_status": normalized.get(latest_life_id, {}).get("life_status"),
        "inconsistencies": inconsistencies,
    }
    return normalized, identities


METRICS_CONTRACT_LABELS: dict[str, str] = {
    "total_lives": "Vies totales",
    "alive_lives": "Vies vivantes",
    "dead_lives": "Vies mortes",
    "selected_lives": "Vies sélectionnées",
    "recent_activity_lives": "Vies avec activité récente",
}


def build_life_counts(lives: dict[str, dict[str, Any]]) -> dict[str, int]:
    """Compute life counters from aggregated comparison payloads."""
    total_lives = len(lives)
    selected_lives = 0
    recent_activity_lives = 0
    dead_lives = 0

    for payload in lives.values():
        if bool(payload.get("selected_life")):
            selected_lives += 1
        if bool(payload.get("has_recent_activity")):
            recent_activity_lives += 1

        life_status = payload.get("life_status")
        registry_status = payload.get("registry_status")
        extinct_in_runs = bool(payload.get("extinction_seen_in_runs"))
        if life_status == "dead" or registry_status == "extinct" or extinct_in_runs:
            dead_lives += 1

    alive_lives = max(total_lives - dead_lives, 0)

    return {
        "total_lives": total_lives,
        "alive_lives": alive_lives,
        "dead_lives": dead_lives,
        "selected_lives": selected_lives,
        "recent_activity_lives": recent_activity_lives,
    }


def build_metrics_contract(lives: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Return counts plus human labels under the dashboard contract schema."""
    return {
        "counts": build_life_counts(lives),
        "labels": METRICS_CONTRACT_LABELS,
    }
