"""Static diagnostics for recent evolution events."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable

RECENT_LIMIT = 200

_RECOMMENDATIONS = {
    "timeout_rate": "Réduisez le coût des skills, bornez les boucles et augmentez les timeouts seulement après profilage.",
    "negative_infinite_scores": "Filtrez les scores non finis avant promotion et corrigez les skills qui retournent -inf/nan.",
    "breaker_open": "Laissez expirer le cooldown, inspectez les dernières violations et baissez temporairement le quota de mutations.",
    "repeated_quarantine": "Désactivez ou réparez les skills en quarantaine répétée puis relancez leur validation sandbox.",
    "invalid_autogen": "Durcissez les prompts/templates autogen et ajoutez une validation syntaxique avant écriture.",
}


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            yield value


def _recent_run_event_files(runs_dir: Path, limit: int) -> list[Path]:
    if not runs_dir.exists():
        return []
    candidates = [path for path in runs_dir.glob("*/events.jsonl") if path.is_file()]
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[:limit]


def load_recent_evolution_events(
    life_home: Path, *, limit: int = RECENT_LIMIT
) -> list[dict[str, Any]]:
    """Load recent events from ``runs/*/events.jsonl`` and ``mem/episodic.jsonl``."""

    events: list[dict[str, Any]] = []
    for path in _recent_run_event_files(life_home / "runs", limit):
        for event in _iter_jsonl(path):
            event.setdefault("source_file", str(path.relative_to(life_home)))
            events.append(event)
    episodic_path = life_home / "mem" / "episodic.jsonl"
    for event in _iter_jsonl(episodic_path):
        event.setdefault("source_file", "mem/episodic.jsonl")
        events.append(event)
    return events[-limit:]


def _event_name(event: dict[str, Any]) -> str:
    return str(event.get("event") or event.get("event_type") or event.get("type") or "")


def _payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else {}


def _contains_timeout(event: dict[str, Any]) -> bool:
    name = _event_name(event).lower()
    data = {**event, **_payload(event)}
    text = json.dumps(data, ensure_ascii=False, default=str).lower()
    return "timeout" in name or "timeout" in text


def _has_negative_inf(event: dict[str, Any]) -> bool:
    for value in [event.get("score"), _payload(event).get("score")]:
        if value == "-inf":
            return True
        if isinstance(value, float) and math.isinf(value) and value < 0:
            return True
    return "-inf" in json.dumps(event, ensure_ascii=False, default=str).lower()


def _count_autogen_invalid(events: list[dict[str, Any]]) -> int:
    total = 0
    for event in events:
        name = _event_name(event).lower()
        text = json.dumps(event, ensure_ascii=False, default=str).lower()
        if "autogen" in name and (
            "invalid" in text or "failed" in name or "validation_failed" in name
        ):
            total += 1
    return total


def analyze_evolution(life_home: Path, *, limit: int = RECENT_LIMIT) -> dict[str, Any]:
    """Return a static diagnostic report for recent evolution patterns."""

    life_home = life_home.expanduser()
    events = load_recent_evolution_events(life_home, limit=limit)
    total = len(events)
    timeout_count = sum(1 for event in events if _contains_timeout(event))
    neg_inf_count = sum(1 for event in events if _has_negative_inf(event))
    breaker_count = sum(
        1 for event in events if "circuit_breaker_opened" in _event_name(event)
    )
    quarantine_count = sum(
        1 for event in events if "quarantin" in _event_name(event).lower()
    )
    autogen_invalid_count = _count_autogen_invalid(events)

    pattern_specs = [
        (
            "timeout_rate",
            timeout_count,
            total > 0 and timeout_count / total >= 0.25,
            f"{timeout_count}/{total}",
        ),
        (
            "negative_infinite_scores",
            neg_inf_count,
            neg_inf_count > 0,
            str(neg_inf_count),
        ),
        ("breaker_open", breaker_count, breaker_count > 0, str(breaker_count)),
        (
            "repeated_quarantine",
            quarantine_count,
            quarantine_count >= 2,
            str(quarantine_count),
        ),
        (
            "invalid_autogen",
            autogen_invalid_count,
            autogen_invalid_count > 0,
            str(autogen_invalid_count),
        ),
    ]
    patterns = [
        {
            "pattern": pattern,
            "detected": bool(detected),
            "count": count,
            "evidence": evidence,
            "recommendation": (
                _RECOMMENDATIONS[pattern]
                if detected
                else "Aucune correction nécessaire."
            ),
        }
        for pattern, count, detected, evidence in pattern_specs
    ]
    return {"life_home": str(life_home), "events_analyzed": total, "patterns": patterns}
