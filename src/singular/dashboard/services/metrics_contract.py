from __future__ import annotations

from typing import Any


METRICS_CONTRACT_LABELS = {
    "total_lives": "Vies totales",
    "alive_lives": "Vies vivantes",
    "dead_lives": "Vies mortes",
    "selected_lives": "Vies sélectionnées",
    "recent_activity_lives": "Vies avec activité récente",
}


def build_life_counts(lives: dict[str, dict[str, Any]]) -> dict[str, int]:
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
        extinct_in_runs = bool(payload.get("extinction_seen_in_runs"))
        if life_status == "extinct" or extinct_in_runs:
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
    return {
        "counts": build_life_counts(lives),
        "labels": METRICS_CONTRACT_LABELS,
    }
