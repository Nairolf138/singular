"""Status command implementation."""

from __future__ import annotations

import json
from pathlib import Path

from ..lives import list_relations
from ..life.health import detect_health_state
from ..life.vital import compute_vital_timeline
from ..metrics.autonomy import compute_autonomy_metrics
from ..psyche import Psyche
from ..memory import get_mem_dir
from ..memory import read_skills
from ..runs.logger import RUNS_DIR
from ..schedulers.reevaluation import alerts_from_records
from ..sensors import compute_host_metrics_aggregates, summarize_environmental_impact
from ..skills_daily import build_daily_skills_snapshot


def _print_table(headers: list[str], rows: list[list[str]]) -> None:
    widths = [len(header) for header in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(cell))

    def _fmt(row: list[str]) -> str:
        return " | ".join(cell.ljust(widths[idx]) for idx, cell in enumerate(row))

    print(_fmt(headers))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(_fmt(row))





def _fmt_ratio(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value) * 100:.1f}%"
    return "-"


def _fmt_number(value: object, unit: str = "") -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.2f}{unit}"
    return "-"



def _read_quest_status() -> dict[str, object]:
    path = get_mem_dir() / "quests_state.json"
    if not path.exists():
        return {"active": [], "paused": [], "completed": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"active": [], "paused": [], "completed": []}
    if not isinstance(payload, dict):
        return {"active": [], "paused": [], "completed": []}
    active = payload.get("active") if isinstance(payload.get("active"), list) else []
    paused = payload.get("paused") if isinstance(payload.get("paused"), list) else []
    completed = payload.get("completed") if isinstance(payload.get("completed"), list) else []
    return {"active": active, "paused": paused, "completed": completed[-20:]}


def _extract_objective_priorities(record: dict[str, object]) -> dict[str, float]:
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


def _build_trajectory_payload(
    *,
    records: list[dict[str, object]],
    quests: dict[str, object],
) -> dict[str, object]:
    active = quests.get("active") if isinstance(quests.get("active"), list) else []
    paused = quests.get("paused") if isinstance(quests.get("paused"), list) else []
    completed = quests.get("completed") if isinstance(quests.get("completed"), list) else []

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

    objective_counts = {
        "in_progress": sum(1 for status in objective_status.values() if status == "in_progress"),
        "abandoned": sum(1 for status in objective_status.values() if status == "abandoned"),
        "completed": sum(1 for status in objective_status.values() if status == "completed"),
    }

    previous: dict[str, float] = {}
    priority_changes: list[dict[str, object]] = []
    for record in records:
        priorities = _extract_objective_priorities(record)
        if not priorities:
            continue
        ts = record.get("ts")
        for objective, new_value in priorities.items():
            old_value = previous.get(objective)
            if old_value is None:
                previous[objective] = new_value
                continue
            if abs(new_value - old_value) >= 0.01:
                priority_changes.append(
                    {
                        "objective": objective,
                        "at": ts if isinstance(ts, str) else None,
                        "from": round(old_value, 4),
                        "to": round(new_value, 4),
                        "delta": round(new_value - old_value, 4),
                    }
                )
                previous[objective] = new_value

    narrative_links: list[dict[str, object]] = []
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
        narrative_links.append(
            {
                "objective": objective,
                "event": record.get("self_narrative_event", event),
                "at": record.get("ts") if isinstance(record.get("ts"), str) else None,
                "run": record.get("_run_file") if isinstance(record.get("_run_file"), str) else None,
            }
        )

    return {
        "objectives": {
            "counts": objective_counts,
            "in_progress": [name for name, status in objective_status.items() if status == "in_progress"],
            "abandoned": [name for name, status in objective_status.items() if status == "abandoned"],
            "completed": [name for name, status in objective_status.items() if status == "completed"],
        },
        "priority_changes": priority_changes[-40:],
        "objective_narrative_links": narrative_links[-40:],
    }


def _read_skill_lifecycle_status() -> dict[str, object]:
    skills = read_skills()
    summary = {
        "active": 0,
        "dormant": 0,
        "archived": 0,
        "temporarily_disabled": 0,
        "deleted": 0,
        "total": 0,
    }
    for raw_entry in skills.values():
        summary["total"] += 1
        state = "active"
        if isinstance(raw_entry, dict):
            lifecycle = raw_entry.get("lifecycle")
            if isinstance(lifecycle, dict) and isinstance(lifecycle.get("state"), str):
                state = lifecycle["state"]
        if state in summary:
            summary[state] += 1
        else:
            summary["active"] += 1
    return summary

def status(*, verbose: bool = False, output_format: str = "plain") -> None:
    """Display basic metrics and current psyche state."""

    payload: dict[str, object] = {
        "latest_run": None,
        "last_execution_ms": None,
        "success_rate": None,
        "mutation_success_rate": None,
        "mutation_count": 0,
        "health": None,
        "alerts": [],
        "mood": None,
        "traits": {},
        "autonomy_metrics": {},
        "quests": {"active": [], "paused": [], "completed": []},
        "trajectory": {
            "objectives": {
                "counts": {"in_progress": 0, "abandoned": 0, "completed": 0},
                "in_progress": [],
                "abandoned": [],
                "completed": [],
            },
            "priority_changes": [],
            "objective_narrative_links": [],
        },
        "skills_lifecycle": {
            "active": 0,
            "dormant": 0,
            "archived": 0,
            "temporarily_disabled": 0,
            "deleted": 0,
            "total": 0,
        },
        "daily_skills": build_daily_skills_snapshot([]),
        "vital_timeline": {
            "age": 0,
            "state": "mature",
            "risk_level": "low",
            "terminal": False,
            "causes": [],
            "reproduction_eligible": False,
            "thresholds": {},
        },
        "host_environment": {
            "aggregates": {},
            "impact": {},
        },
        "relationships": {},
    }
    host_aggregates = compute_host_metrics_aggregates()
    payload["host_environment"] = {
        "aggregates": host_aggregates,
        "impact": summarize_environmental_impact(host_aggregates),
    }
    all_records: list[dict[str, object]] = []
    runs_dir = Path(RUNS_DIR)
    files = sorted(runs_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    if files:
        latest = files[-1]
        for run_file in files:
            with run_file.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        all_records.append(json.loads(line))
        records = []
        with latest.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        payload["daily_skills"] = build_daily_skills_snapshot(records=all_records)
        if records:
            last = records[-1]
            ms_new = last.get("ms_new")
            mutation_records = [r for r in records if "score_new" in r]
            mutation_count = len(mutation_records)
            success_records = [
                r
                for r in records
                if "score_new" in r or isinstance(r.get("ok"), bool)
            ]
            ok_count = sum(1 for r in success_records if r.get("ok") is True)
            success_rate = (
                ok_count / len(success_records) * 100 if success_records else None
            )
            health_scores = [
                float(h["score"])
                for r in mutation_records
                for h in [r.get("health", {})]
                if isinstance(h, dict) and isinstance(h.get("score"), (int, float))
            ]
            state = detect_health_state(health_scores, short_window=10, long_window=50)
            payload["latest_run"] = latest.stem
            payload["last_execution_ms"] = (
                round(float(ms_new), 2) if isinstance(ms_new, (int, float)) else None
            )
            payload["success_rate"] = (
                round(success_rate, 2) if success_rate is not None else None
            )
            payload["mutation_success_rate"] = (
                round(success_rate, 2) if success_rate is not None else None
            )
            payload["mutation_count"] = mutation_count
            if health_scores:
                payload["health"] = {
                    "score": round(health_scores[-1], 2),
                    "trend": state,
                    "window": "10/50",
                }
            payload["autonomy_metrics"] = compute_autonomy_metrics(records)
            failure_streak = 0
            max_failure_streak = 0
            for rec in records:
                accepted = rec.get("accepted")
                if not isinstance(accepted, bool):
                    accepted = rec.get("ok")
                if accepted is False:
                    failure_streak += 1
                    max_failure_streak = max(max_failure_streak, failure_streak)
                elif accepted is True:
                    failure_streak = 0
            payload["vital_timeline"] = compute_vital_timeline(
                age=mutation_count,
                current_health=health_scores[-1] if health_scores else None,
                failure_rate=(1 - (ok_count / len(success_records))) if success_records else None,
                failure_streak=max_failure_streak,
                extinction_seen=any(r.get("event") == "death" for r in records),
            )
            if verbose:
                alerts = alerts_from_records(records)
                payload["alerts"] = alerts
    payload.setdefault("alerts", [])

    psyche = Psyche.load_state()
    mood = psyche.last_mood.value if psyche.last_mood else "neutral"
    payload["mood"] = mood
    payload["quests"] = _read_quest_status()
    payload["trajectory"] = _build_trajectory_payload(
        records=all_records if "all_records" in locals() else [],
        quests=payload["quests"] if isinstance(payload["quests"], dict) else {},
    )
    payload["skills_lifecycle"] = _read_skill_lifecycle_status()
    payload["traits"] = {
        "curiosity": round(psyche.curiosity, 2),
        "patience": round(psyche.patience, 2),
        "playfulness": round(psyche.playfulness, 2),
        "optimism": round(psyche.optimism, 2),
        "resilience": round(psyche.resilience, 2),
    }
    try:
        payload["relationships"] = list_relations(None)
    except KeyError:
        payload["relationships"] = {}

    if output_format == "json":
        print(json.dumps(payload, ensure_ascii=False))
        return

    if output_format == "table":
        autonomy = payload.get("autonomy_metrics") if isinstance(payload.get("autonomy_metrics"), dict) else {}
        decision_quality = autonomy.get("decision_quality") if isinstance(autonomy.get("decision_quality"), dict) else {}
        run_rows = [
            ["Latest run", str(payload.get("latest_run") or "-")],
            ["Last execution speed", f"{payload['last_execution_ms']}ms" if payload.get("last_execution_ms") is not None else "-"],
            ["Success rate", f"{payload['success_rate']}%" if payload.get("success_rate") is not None else "-"],
            [
                "Mutation success rate",
                (
                    f"{payload['mutation_success_rate']}%"
                    if payload.get("mutation_success_rate") is not None
                    else "-"
                ),
            ],
            ["Mutation count", str(payload.get("mutation_count") or 0)],
            [
                "Health score",
                (
                    f"{payload['health']['score']}/100 ({payload['health']['trend']}, fenêtres {payload['health']['window']})"
                    if isinstance(payload.get("health"), dict)
                    else "-"
                ),
            ],
            ["Taux d’initiatives proactives", _fmt_ratio(autonomy.get("proactive_initiative_rate"))],
            ["Stabilité long terme", _fmt_ratio(autonomy.get("long_term_stability"))],
            [
                "Qualité décisions (acceptation/régression)",
                f"{_fmt_ratio(decision_quality.get('acceptance_rate'))} / {_fmt_ratio(decision_quality.get('regression_rate'))}",
            ],
            ["Latence perception→action", _fmt_number(autonomy.get("perception_to_action_latency_ms"), " ms")],
            ["Coût ressources par gain", _fmt_number(autonomy.get("resource_cost_per_gain"))],
            ["Mood", str(payload.get("mood"))],
            [
                "Arbre familial (nœuds)",
                str(len((((payload.get("relationships") or {}).get("family") or {}).get("nodes") or []))),
            ],
            [
                "Réseau social (liens)",
                str(len((((payload.get("relationships") or {}).get("social") or {}).get("edges") or []))),
            ],
            [
                "Conflits actifs",
                str(len((payload.get("relationships") or {}).get("active_conflicts", []))),
            ],
            ["Quêtes actives", str(len((payload.get("quests") or {}).get("active", [])))],
            ["Quêtes terminées", str(len((payload.get("quests") or {}).get("completed", [])))],
            ["Skills actives", str((payload.get("skills_lifecycle") or {}).get("active", 0))],
            ["Skills dormantes", str((payload.get("skills_lifecycle") or {}).get("dormant", 0))],
            ["Skills archivées", str((payload.get("skills_lifecycle") or {}).get("archived", 0))],
            [
                "Top skill quotidienne",
                (
                    str(((payload.get("daily_skills") or {}).get("top_skills") or [{}])[0].get("skill") or "-")
                    if ((payload.get("daily_skills") or {}).get("top_skills") or [])
                    else "-"
                ),
            ],
            [
                "Fréquence skills (24h/7j)",
                (
                    f"{((payload.get('daily_skills') or {}).get('frequency_totals') or {}).get('uses_24h', 0)} / "
                    f"{((payload.get('daily_skills') or {}).get('frequency_totals') or {}).get('uses_7d', 0)}"
                ),
            ],
            [
                "Progression apprise→utilisée→améliorée",
                (
                    f"{((payload.get('daily_skills') or {}).get('progression_pipeline') or {}).get('learned', 0)} → "
                    f"{((payload.get('daily_skills') or {}).get('progression_pipeline') or {}).get('used', 0)} → "
                    f"{((payload.get('daily_skills') or {}).get('progression_pipeline') or {}).get('improved', 0)}"
                ),
            ],
            ["Âge vital", str((payload.get("vital_timeline") or {}).get("age", 0))],
            ["État vital", str((payload.get("vital_timeline") or {}).get("state", "n/a"))],
            ["Risque vital", str((payload.get("vital_timeline") or {}).get("risk_level", "n/a"))],
            [
                "Impact environnement hôte",
                str(((payload.get("host_environment") or {}).get("impact") or {}).get("impact_level", "low")),
            ],
            [
                "Biais décisionnel hôte",
                str(((payload.get("host_environment") or {}).get("impact") or {}).get("decision_bias", "balanced")),
            ],
        ]
        _print_table(["Metric", "Value"], run_rows)
        if verbose:
            alerts = payload.get("alerts") or []
            if alerts:
                alert_rows = [
                    [str(a.get("level", "?")), str(a.get("message", "")), str(a.get("action", ""))]
                    for a in alerts
                ]
                print("Alerts")
                _print_table(["Level", "Message", "Action"], alert_rows)
            else:
                print("Alerts: none")
        trait_rows = [[k, f"{v:.2f}"] for k, v in payload["traits"].items()]
        print("Traits")
        _print_table(["Trait", "Value"], trait_rows)
        return

    if payload.get("latest_run") is None:
        print("No run logs found.")
    else:
        print(f"Latest run: {payload['latest_run']}")
        if payload.get("last_execution_ms") is not None:
            print(f"Last execution speed: {payload['last_execution_ms']:.2f}ms")
        if payload.get("success_rate") is not None:
            print(f"Success rate: {payload['success_rate']:.0f}%")
        if payload.get("mutation_success_rate") is not None:
            print(f"Mutation success rate: {payload['mutation_success_rate']:.0f}%")
        print(f"Mutation count: {payload['mutation_count']}")
        autonomy = payload.get("autonomy_metrics") if isinstance(payload.get("autonomy_metrics"), dict) else {}
        decision_quality = autonomy.get("decision_quality") if isinstance(autonomy.get("decision_quality"), dict) else {}
        print(f"Taux d’initiatives proactives: {_fmt_ratio(autonomy.get('proactive_initiative_rate'))}")
        print(f"Stabilité long terme: {_fmt_ratio(autonomy.get('long_term_stability'))}")
        print(
            "Qualité décisions (acceptation/régression): "
            f"{_fmt_ratio(decision_quality.get('acceptance_rate'))} / {_fmt_ratio(decision_quality.get('regression_rate'))}"
        )
        print(f"Latence perception→action: {_fmt_number(autonomy.get('perception_to_action_latency_ms'), ' ms')}")
        print(f"Coût ressources par gain: {_fmt_number(autonomy.get('resource_cost_per_gain'))}")
        vital = payload.get("vital_timeline") if isinstance(payload.get("vital_timeline"), dict) else {}
        print(f"Âge vital: {vital.get('age', 0)}")
        print(f"État vital: {vital.get('state', 'n/a')}")
        print(f"Risque vital: {vital.get('risk_level', 'n/a')}")
        host_environment = payload.get("host_environment") if isinstance(payload.get("host_environment"), dict) else {}
        host_impact = host_environment.get("impact") if isinstance(host_environment.get("impact"), dict) else {}
        print(f"Impact environnement hôte: {host_impact.get('impact_level', 'low')}")
        print(f"Biais décisionnel hôte: {host_impact.get('decision_bias', 'balanced')}")
        causes = vital.get("causes")
        if isinstance(causes, list) and causes:
            print(f"Causes observées: {', '.join(str(c) for c in causes)}")
        health = payload.get("health")
        if isinstance(health, dict):
            print(
                "Health score: "
                f"{health['score']:.2f}/100 ({health['trend']}, fenêtres {health['window']})"
            )
        if verbose:
            alerts = payload.get("alerts") or []
            if alerts:
                print("Alerts:")
                for alert in alerts:
                    print(
                        f"  - [{alert['level']}] {alert['message']} "
                        f"(action: {alert['action']})"
                    )
            else:
                print("Alerts: none")

    print(f"Mood: {payload['mood']}")
    relationships = payload.get("relationships") if isinstance(payload.get("relationships"), dict) else {}
    family = relationships.get("family") if isinstance(relationships.get("family"), dict) else {}
    social = relationships.get("social") if isinstance(relationships.get("social"), dict) else {}
    print(f"Arbre familial: {len(family.get('nodes', []))} nœuds")
    print(f"Réseau social: {len(social.get('edges', []))} relations")
    print(f"Conflits actifs: {len(relationships.get('active_conflicts', []))}")
    quests = payload.get("quests") if isinstance(payload.get("quests"), dict) else {"active": [], "completed": []}
    print(f"Quêtes actives: {len(quests.get('active', []))}")
    print(f"Quêtes terminées: {len(quests.get('completed', []))}")
    lifecycle = payload.get("skills_lifecycle") if isinstance(payload.get("skills_lifecycle"), dict) else {}
    print(f"Skills actives: {lifecycle.get('active', 0)}")
    print(f"Skills dormantes: {lifecycle.get('dormant', 0)}")
    print(f"Skills archivées: {lifecycle.get('archived', 0)}")
    print("Traits:")
    for trait, value in payload["traits"].items():
        print(f"  {trait}: {value:.2f}")
