from __future__ import annotations

# mypy: ignore-errors

import asyncio
from collections import Counter
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
import sys
from pathlib import Path
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from singular.lives import get_registry_root, load_registry, set_life_status
from singular.life.vital import compute_vital_timeline
from singular.metrics.autonomy import compute_autonomy_metrics
from singular.memory import read_causal_timeline, read_skills
from singular.storage_retention import retention_status_snapshot

from singular.dashboard.actions import DashboardActionService
from singular.governance.policy import load_runtime_policy
from singular.skills_daily import build_daily_skills_snapshot
from fastapi.responses import HTMLResponse

from singular.schedulers.reevaluation import alerts_from_records
from singular.dashboard.repositories.run_records import RunRecordsRepository
from singular.dashboard.services.trajectory import (
    build_trajectory as build_trajectory_service,
    extract_objective_priorities as extract_objective_priorities_service,
)
from singular.dashboard.services.lives_comparison import (
    aggregate_lives as aggregate_lives_service,
    compute_liveness_index as compute_liveness_index_service,
    parse_ts as parse_ts_service,
    resolve_time_window_cutoff as resolve_time_window_cutoff_service,
    life_trend_label as life_trend_label_service,
    life_trend_rank as life_trend_rank_service,
)
from singular.dashboard.services.metrics_contract import (
    build_metrics_contract as build_metrics_contract_service,
)
from singular.dashboard.services.code_evolution import (
    aggregate_code_evolution as aggregate_code_evolution_service,
)


@dataclass
class _LogCursor:
    inode: int | None
    offset: int


def create_app(
    runs_dir: Path | str | None = None, psyche_file: Path | str | None = None
) -> FastAPI:
    """Create the dashboard FastAPI application."""
    registry_root = get_registry_root()
    base_dir = Path(os.environ.get("SINGULAR_HOME", registry_root))
    runs_path = Path(runs_dir) if runs_dir is not None else None
    psyche_path = (
        Path(psyche_file)
        if psyche_file is not None
        else base_dir / "mem" / "psyche.json"
    )
    quests_path = base_dir / "mem" / "quests_state.json"
    app = FastAPI()
    actions = DashboardActionService(home=base_dir)
    templates_dir = Path(__file__).parent / "templates"
    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="dashboard-static")
    run_repository = RunRecordsRepository(
        base_dir=base_dir,
        runs_path=runs_path,
        registry_loader=load_registry,
    )

    def _render_template(name: str, replacements: dict[str, str] | None = None) -> str:
        template = (templates_dir / name).read_text(encoding="utf-8")
        for key, value in (replacements or {}).items():
            template = template.replace(key, value)
        return template

    def _registry_lives_paths() -> list[Path]:
        registry = load_registry()
        raw_lives = registry.get("lives")
        if not isinstance(raw_lives, dict):
            return []
        lives_paths: list[Path] = []
        for meta in raw_lives.values():
            path = getattr(meta, "path", None)
            if isinstance(path, Path):
                lives_paths.append(path)
        return lives_paths

    def _resolve_life_dir(life: str) -> Path | None:
        registry = load_registry()
        raw_lives = registry.get("lives")
        if not isinstance(raw_lives, dict):
            return None
        for slug, meta in raw_lives.items():
            if not isinstance(slug, str):
                continue
            path_value = getattr(meta, "path", None)
            display_name = getattr(meta, "name", None)
            if isinstance(meta, dict):
                path_value = meta.get("path", path_value)
                display_name = meta.get("name", display_name)
            if isinstance(path_value, str):
                path_value = Path(path_value)
            if not isinstance(path_value, Path):
                continue
            if life in {slug, str(display_name)}:
                return path_value
        return None

    def _registry_overview() -> dict[str, object]:
        registry = load_registry()
        raw_lives = registry.get("lives")
        lives = raw_lives if isinstance(raw_lives, dict) else {}
        active = registry.get("active")
        active_valid = isinstance(active, str) and active in lives
        is_empty = not lives and active is None
        onboarding_message = "Aucune vie, créez-en une." if is_empty else None
        return {
            "lives": lives,
            "lives_count": len(lives),
            "active": active,
            "active_valid": active_valid,
            "is_empty": is_empty,
            "onboarding_message": onboarding_message,
        }

    def _runs_dirs(current_life_only: bool = False) -> list[Path]:
        return run_repository.runs_dirs(current_life_only=current_life_only)

    def _load_run_records(current_life_only: bool = False) -> list[dict[str, object]]:
        return run_repository.load_run_records(current_life_only=current_life_only)

    def _is_mutation_record(record: dict[str, object]) -> bool:
        return any(
            field in record
            for field in ("score_base", "score_new", "ok", "accepted", "op", "operator")
        )

    def _as_float(value: object) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        return None

    def _extract_objective_priorities(record: dict[str, object]) -> dict[str, float]:
        return extract_objective_priorities_service(record)

    def _build_trajectory(records: list[dict[str, object]]) -> dict[str, object]:
        return build_trajectory_service(
            records=records,
            quests_path=quests_path,
            record_run_id=_record_run_id,
        )

    def _record_run_id(record: dict[str, object]) -> str:
        run_id = record.get("run_id")
        if isinstance(run_id, str) and run_id:
            return run_id
        run = record.get("_run_file")
        if not isinstance(run, str):
            return "unknown"
        normalized = run.strip()
        if not normalized:
            return "unknown"
        # Legacy JSONL files often follow <run_id>-<timestamp>.jsonl.
        # Normalize back to <run_id> so registry run mappings can resolve life names.
        if "-" in normalized:
            candidate, suffix = normalized.rsplit("-", 1)
            if candidate and suffix.isdigit() and len(suffix) >= 8:
                return candidate
        return normalized

    def _registry_run_to_life_mapping() -> dict[str, str]:
        registry = load_registry()
        mapping: dict[str, str] = {}
        lives = registry.get("lives")
        if not isinstance(lives, dict):
            return mapping

        for slug, metadata in lives.items():
            if not isinstance(slug, str):
                continue
            candidates: list[object] = []
            if isinstance(metadata, dict):
                candidates.extend(
                    [
                        metadata.get("run_id"),
                        metadata.get("last_run_id"),
                        metadata.get("run"),
                    ]
                )
                run_ids = metadata.get("run_ids")
                if isinstance(run_ids, list):
                    candidates.extend(run_ids)
                runs = metadata.get("runs")
                if isinstance(runs, list):
                    candidates.extend(runs)
            for candidate in candidates:
                if isinstance(candidate, str) and candidate:
                    mapping[candidate] = slug
        return mapping

    def _record_life(record: dict[str, object]) -> str:
        if isinstance(record.get("life"), str):
            return str(record["life"])
        skill = record.get("skill")
        if isinstance(skill, str) and ":" in skill:
            return skill.split(":", 1)[0]
        run_id = _record_run_id(record)
        if run_id != "unknown":
            mapped_life = _registry_run_to_life_mapping().get(run_id)
            if isinstance(mapped_life, str) and mapped_life:
                return mapped_life
        return "unknown"

    def _parse_iso8601(value: object) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _iso_or_none(value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.astimezone(timezone.utc).isoformat()

    def _compute_ecosystem(current_life_only: bool = False) -> dict:
        organisms: dict[str, dict[str, object]] = {}
        for directory in _runs_dirs(current_life_only=current_life_only):
            if not directory.exists():
                continue
            for file in directory.iterdir():
                if not file.is_file() or file.suffix != ".jsonl":
                    continue
                for line in file.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    event = record.get("event")
                    interaction = record.get("interaction")

                    if event == "interaction" and isinstance(
                        record.get("organism"), str
                    ):
                        name = str(record["organism"])
                        state = organisms.setdefault(name, {"status": "alive"})
                        if "energy" in record:
                            state["energy"] = record["energy"]
                        if "resources" in record:
                            state["resources"] = record["resources"]
                        if "score" in record:
                            state["score"] = record["score"]
                        if "alive" in record:
                            state["status"] = (
                                "alive" if bool(record["alive"]) else "extinct"
                            )
                        if interaction:
                            state["last_interaction"] = interaction
                    elif event == "death":
                        skill = str(record.get("skill", ""))
                        if ":" in skill:
                            name, _ = skill.split(":", 1)
                            state = organisms.setdefault(name, {})
                            state["status"] = "extinct"
                    elif event is None and isinstance(record.get("skill"), str):
                        skill = record["skill"]
                        if ":" in skill:
                            name, _ = skill.split(":", 1)
                            state = organisms.setdefault(name, {"status": "alive"})
                            state["score"] = record.get("score_new")

        alive = sum(1 for state in organisms.values() if state.get("status") != "extinct")
        total_energy = sum(
            float(state.get("energy", 0.0))
            for state in organisms.values()
            if isinstance(state.get("energy"), (int, float))
        )
        total_resources = sum(
            float(state.get("resources", 0.0))
            for state in organisms.values()
            if isinstance(state.get("resources"), (int, float))
        )
        comparison, _ = _aggregate_lives(current_life_only=current_life_only)
        life_metrics_contract = build_metrics_contract_service(comparison)
        life_counts = life_metrics_contract.get("counts", {})
        return {
            "organisms": organisms,
            "summary": {
                "total_organisms": int(life_counts.get("total_lives", len(organisms))),
                "alive_organisms": int(life_counts.get("alive_lives", alive)),
                "total_energy": total_energy,
                "total_resources": total_resources,
            },
            "life_metrics_contract": life_metrics_contract,
        }

    def _skill_lifecycle_summary() -> dict[str, int]:
        payload = {"active": 0, "dormant": 0, "archived": 0, "temporarily_disabled": 0, "deleted": 0, "total": 0}
        for raw_entry in read_skills().values():
            payload["total"] += 1
            state = "active"
            if isinstance(raw_entry, dict):
                lifecycle = raw_entry.get("lifecycle")
                if isinstance(lifecycle, dict) and isinstance(lifecycle.get("state"), str):
                    state = lifecycle["state"]
            if state in payload:
                payload[state] += 1
            else:
                payload["active"] += 1
        return payload

    def _iter_run_files(current_life_only: bool = False) -> list[Path]:
        return run_repository.iter_run_files(current_life_only=current_life_only)

    def _read_jsonl_records(file: Path) -> list[dict[str, object]]:
        return run_repository.read_jsonl_records(file)

    def _latest_run_file(current_life_only: bool = False) -> Path | None:
        return run_repository.latest_run_file(current_life_only=current_life_only)

    def _resolve_run_file(run_id: str, current_life_only: bool = False) -> Path | None:
        return run_repository.resolve_run_file(run_id, current_life_only=current_life_only)

    def _resolve_consciousness_path(run_id: str, current_life_only: bool = False) -> Path | None:
        return run_repository.resolve_consciousness_path(run_id, current_life_only=current_life_only)

    def _parse_ts(value: object) -> datetime | None:
        return parse_ts_service(value)

    def _resolve_time_window_cutoff(time_window: str) -> datetime | None:
        return resolve_time_window_cutoff_service(time_window)

    def _event_type(record: dict[str, object]) -> str | None:
        event = record.get("event")
        if isinstance(event, str):
            return event
        if _is_mutation_record(record):
            return "mutation"
        return None

    def _record_organism(record: dict[str, object]) -> str | None:
        organism = record.get("organism")
        if isinstance(organism, str):
            return organism
        return _record_life(record)

    def _timeline_entry(record: dict[str, object], run_id: str) -> dict[str, object] | None:
        event = _event_type(record)
        if event not in {"mutation", "delay", "refuse", "death", "interaction"}:
            return None

        accepted: bool | None = None
        accepted_value = record.get("accepted")
        if isinstance(accepted_value, bool):
            accepted = accepted_value
        elif isinstance(record.get("ok"), bool):
            accepted = bool(record.get("ok"))

        score_before = _as_float(record.get("score_base"))
        score_after = _as_float(record.get("score_new"))

        return {
            "run_id": run_id,
            "timestamp": record.get("ts"),
            "event": event,
            "organism": _record_organism(record),
            "operator": record.get("operator", record.get("op")),
            "accepted": accepted,
            "human_summary": record.get("human_summary"),
            "decision_reason": record.get("decision_reason", record.get("reason")),
            "diff": record.get("diff"),
            "loop_modifications": record.get("loop_modifications", {}),
            "score_before": score_before,
            "score_after": score_after,
            "interaction": record.get("interaction"),
            "resume_at": record.get("resume_at"),
        }

    def _normalize_mutation_metrics(record: dict[str, object]) -> dict[str, object]:
        metrics = record.get("mutation_metrics")
        if not isinstance(metrics, dict):
            metrics = {}

        lines_added = metrics.get("lines_added", record.get("lines_added"))
        lines_removed = metrics.get("lines_removed", record.get("lines_removed"))
        functions_modified = metrics.get(
            "functions_modified", record.get("functions_modified")
        )

        return {
            "lines_added": lines_added if isinstance(lines_added, int) else 0,
            "lines_removed": lines_removed if isinstance(lines_removed, int) else 0,
            "functions_modified": (
                functions_modified if isinstance(functions_modified, list) else []
            ),
        }

    def _mutation_detail(record: dict[str, object], run_id: str, index: int) -> dict[str, object]:
        metrics = _normalize_mutation_metrics(record)
        return {
            "run_id": run_id,
            "index": index,
            "timestamp": record.get("ts"),
            "operator": record.get("operator", record.get("op")),
            "organism": _record_organism(record),
            "human_summary": record.get("human_summary"),
            "decision_reason": record.get("decision_reason", record.get("reason")),
            "diff": record.get("diff"),
            "metrics": {
                **metrics,
                "ast_before": record.get("ast_before"),
                "ast_after": record.get("ast_after"),
            },
            "impact": {
                "score_before": _as_float(record.get("score_base")),
                "score_after": _as_float(record.get("score_new")),
                "perf_ms_before": _as_float(record.get("ms_base")),
                "perf_ms_after": _as_float(record.get("ms_new")),
                "health_before": _as_float(record.get("health_base")),
                "health_after": _as_float(record.get("health_new")),
            },
        }

    def _summarize_cockpit(current_life_only: bool = False) -> dict[str, object]:
        latest = _latest_run_file(current_life_only=current_life_only)
        if latest is None:
            empty = {
                "run": None,
                "health_score": None,
                "trend": "plateau",
                "accepted_mutation_rate": None,
                "critical_alerts": [],
                "last_notable_mutation": None,
                "next_action": "Aucune donnée: démarrer un run pour remplir le cockpit.",
                "suggested_actions": [
                    "Lancer un run de base",
                    "Vérifier la collecte des métriques",
                ],
                "global_status": "unknown",
                "autonomy_metrics": {},
                "vital_metrics": {
                    "circadian_cycle": {"phase": "indéterminée", "hour_utc": None},
                    "active_objectives": {"count": 0, "items": []},
                    "energy_resources": {
                        "total_energy": 0.0,
                        "total_resources": 0.0,
                        "alive_organisms": 0,
                        "total_organisms": 0,
                    },
                    "code_generation": {
                        "progression": "n/a",
                        "accepted": 0,
                        "rejected": 0,
                        "success_rate": None,
                        "risk_level": "n/a",
                    },
                    "risks": [],
                },
                "vital_timeline": compute_vital_timeline(
                    age=0,
                    current_health=None,
                    failure_rate=None,
                    failure_streak=0,
                    extinction_seen=False,
                ),
                "skills_lifecycle": _skill_lifecycle_summary(),
                "daily_skills": build_daily_skills_snapshot([]),
                "life_metrics_contract": _build_metrics_contract({}),
                "trajectory": _build_trajectory([]),
                "life_liveness_index": 0.0,
                "life_liveness_components": {},
                "life_liveness_proofs": [],
                "life_liveness_life": None,
            }
            return empty

        records = _read_jsonl_records(latest)
        mutations = [record for record in records if _is_mutation_record(record)]

        accepted_values: list[bool] = []
        for record in mutations:
            accepted = record.get("accepted")
            if not isinstance(accepted, bool):
                accepted = record.get("ok")
            if isinstance(accepted, bool):
                accepted_values.append(accepted)

        accepted_rate = None
        if accepted_values:
            accepted_rate = sum(1 for value in accepted_values if value) / len(accepted_values)

        health_scores: list[float] = []
        for record in records:
            health = record.get("health")
            if isinstance(health, dict):
                score = _as_float(health.get("score"))
                if score is not None:
                    health_scores.append(score)
        health_score = health_scores[-1] if health_scores else None

        trend = "plateau"
        if len(health_scores) >= 2:
            window = health_scores[-5:]
            first = window[0]
            last = window[-1]
            if last > first + 1.0:
                trend = "amélioration"
            elif last < first - 1.0:
                trend = "dégradation"

        alerts = alerts_from_records(records)
        critical_alerts = [
            alert
            for alert in alerts
            if str(alert.get("severity", "")).lower() in {"critical", "high"}
        ]

        last_notable_mutation = None
        for record in reversed(mutations):
            score_base = _as_float(record.get("score_base"))
            score_new = _as_float(record.get("score_new"))
            delta = None
            if score_base is not None and score_new is not None:
                delta = score_base - score_new
            if isinstance(delta, (int, float)) and abs(delta) >= 1.0:
                accepted = record.get("accepted")
                if not isinstance(accepted, bool):
                    accepted = record.get("ok")
                last_notable_mutation = {
                    "timestamp": record.get("ts"),
                    "operator": record.get("operator", record.get("op")),
                    "accepted": accepted,
                    "impact_delta": delta,
                    "life": _record_life(record),
                }
                break

        suggested_actions: list[str] = []
        alert_kinds = {str(alert.get("kind", "")) for alert in critical_alerts}
        if "sandbox_failures_rising" in alert_kinds:
            suggested_actions.append("Vérifier provider et sandbox (timeouts, quotas, erreurs IO)")
        if "prolonged_stagnation" in alert_kinds:
            suggested_actions.append("Changer run-id et réduire l'exploration agressive")
        if "health_decline" in alert_kinds:
            suggested_actions.append("Ralentir l'exploration et privilégier les mutations sûres")
        if not suggested_actions:
            suggested_actions.append("Continuer avec les paramètres actuels et surveiller les alertes")

        next_action = suggested_actions[0]
        if critical_alerts:
            global_status = "critical"
        elif trend == "dégradation":
            global_status = "warning"
        else:
            global_status = "stable"

        autonomy_metrics = compute_autonomy_metrics(records)
        ecosystem = _compute_ecosystem(current_life_only=current_life_only)
        summary = ecosystem.get("summary", {}) if isinstance(ecosystem, dict) else {}
        metrics_contract = (
            ecosystem.get("life_metrics_contract", {})
            if isinstance(ecosystem.get("life_metrics_contract"), dict)
            else {}
        )
        life_counts = (
            metrics_contract.get("counts", {})
            if isinstance(metrics_contract.get("counts"), dict)
            else {}
        )

        hour_utc = datetime.now(timezone.utc).hour
        if 5 <= hour_utc < 12:
            circadian_phase = "matin"
        elif 12 <= hour_utc < 18:
            circadian_phase = "jour"
        elif 18 <= hour_utc < 23:
            circadian_phase = "soir"
        else:
            circadian_phase = "nuit"

        trajectory = _build_trajectory(records)
        objectives = trajectory.get("objectives", {}) if isinstance(trajectory.get("objectives"), dict) else {}
        in_progress_names = objectives.get("in_progress") if isinstance(objectives.get("in_progress"), list) else []
        active_objectives = [{"name": name} for name in in_progress_names if isinstance(name, str)]

        accepted_count = sum(1 for value in accepted_values if value is True)
        rejected_count = sum(1 for value in accepted_values if value is False)
        code_risk = "faible"
        if critical_alerts:
            code_risk = "élevé"
        elif trend == "dégradation" or (accepted_rate is not None and accepted_rate < 0.5):
            code_risk = "modéré"

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
        vital_timeline = compute_vital_timeline(
            age=len(mutations),
            current_health=health_score,
            failure_rate=(1 - accepted_rate) if accepted_rate is not None else None,
            failure_streak=max_failure_streak,
            extinction_seen=any(rec.get("event") == "death" for rec in records),
        )
        comparison, _ = _aggregate_lives(current_life_only=current_life_only)
        comparison_rows = [
            {"life": life_name, **payload}
            for life_name, payload in comparison.items()
            if isinstance(payload, dict)
        ]
        selected_row = next(
            (
                row
                for row in comparison_rows
                if row.get("selected_life") is True and isinstance(row.get("life"), str)
            ),
            None,
        )
        if selected_row is None and comparison_rows:
            selected_row = max(
                comparison_rows,
                key=lambda row: float(row.get("life_liveness_index") or 0.0),
            )
        selected_life = selected_row.get("life") if isinstance(selected_row, dict) else None
        filtered_records = [
            record for record in records if selected_life and _record_life(record) == selected_life
        ]
        liveness_payload = (
            compute_liveness_index_service(filtered_records or records)
            if records
            else {"index": 0.0, "components": {}, "proofs": []}
        )

        return {
            "run": latest.stem,
            "health_score": health_score,
            "trend": trend,
            "accepted_mutation_rate": accepted_rate,
            "critical_alerts": critical_alerts,
            "last_notable_mutation": last_notable_mutation,
            "next_action": next_action,
            "suggested_actions": suggested_actions,
            "global_status": global_status,
            "autonomy_metrics": autonomy_metrics,
            "vital_metrics": {
                "circadian_cycle": {"phase": circadian_phase, "hour_utc": hour_utc},
                "active_objectives": {
                    "count": len(active_objectives),
                    "items": active_objectives[:5],
                },
                "energy_resources": {
                    "total_energy": float(summary.get("total_energy", 0.0) or 0.0),
                    "total_resources": float(summary.get("total_resources", 0.0) or 0.0),
                    "alive_organisms": int(
                        life_counts.get("alive_lives", summary.get("alive_organisms", 0))
                        or 0
                    ),
                    "total_organisms": int(
                        life_counts.get("total_lives", summary.get("total_organisms", 0))
                        or 0
                    ),
                },
                "code_generation": {
                    "progression": trend,
                    "accepted": accepted_count,
                    "rejected": rejected_count,
                    "success_rate": accepted_rate,
                    "risk_level": code_risk,
                },
                "risks": [str(alert.get("kind", "")) for alert in critical_alerts],
            },
            "vital_timeline": vital_timeline,
            "skills_lifecycle": _skill_lifecycle_summary(),
            "daily_skills": build_daily_skills_snapshot(records),
            "life_metrics_contract": metrics_contract,
            "trajectory": trajectory,
            "life_liveness_index": liveness_payload.get("index", 0.0),
            "life_liveness_components": liveness_payload.get("components", {}),
            "life_liveness_proofs": liveness_payload.get("proofs", []),
            "life_liveness_life": selected_life,
        }

    def _summarize_cockpit_essential(current_life_only: bool = False) -> dict[str, object]:
        cockpit = _summarize_cockpit(current_life_only=current_life_only)
        comparison, _ = _aggregate_lives(current_life_only=current_life_only)
        rows = comparison.get("table", []) if isinstance(comparison.get("table"), list) else []
        selected_life = "Aucune"
        for row in rows:
            if isinstance(row, dict) and row.get("selected_life") is True:
                candidate = row.get("life")
                if isinstance(candidate, str) and candidate:
                    selected_life = candidate
                    break
        incidents_count = 0
        critical_alerts = cockpit.get("critical_alerts")
        if isinstance(critical_alerts, list):
            incidents_count = len(critical_alerts)
        return {
            "schema_version": "2026-04-15",
            "global_status": cockpit.get("global_status", "unknown"),
            "critical_alerts_count": incidents_count,
            "next_action": cockpit.get("next_action") or "Aucune action immédiate",
            "selected_life": selected_life,
            "active_incidents_count": incidents_count,
        }


    @app.get("/logs")
    def read_logs(current_life_only: bool = False) -> dict[str, str]:
        logs: dict[str, str] = {}
        prefix_paths = runs_path is None
        for directory in _runs_dirs(current_life_only=current_life_only):
            if not directory.exists():
                continue
            for file in directory.iterdir():
                if file.is_file():
                    key = f"{directory.parent.name}/{file.name}" if prefix_paths else file.name
                    logs[key] = file.read_text()
        return logs

    @app.get("/psyche")
    def read_psyche() -> dict:
        if not psyche_path.exists():
            raise HTTPException(status_code=404, detail="psyche.json not found")
        return json.loads(psyche_path.read_text())


    @app.get("/quests")
    def read_quests() -> dict:
        if not quests_path.exists():
            return {"active": [], "completed": []}
        try:
            data = json.loads(quests_path.read_text())
        except json.JSONDecodeError:
            return {"active": [], "completed": []}
        if not isinstance(data, dict):
            return {"active": [], "completed": []}
        active = data.get("active") if isinstance(data.get("active"), list) else []
        completed = data.get("completed") if isinstance(data.get("completed"), list) else []
        return {"active": active, "completed": completed[-20:]}

    def _normalize_work_item(
        payload: dict[str, object], *, fallback_title: str, default_owner: str
    ) -> dict[str, str]:
        def _pick(*keys: str) -> str | None:
            for key in keys:
                value = payload.get(key)
                if value is None:
                    continue
                text = str(value).strip()
                if text:
                    return text
            return None

        return {
            "title": _pick("title", "name", "objective") or fallback_title,
            "status": _pick("status", "result", "decision") or "unknown",
            "last_update": _pick("last_update", "updated_at", "completed_at", "started_at", "ts")
            or "Non disponible",
            "next_step": _pick("next_step", "next_action", "objective", "action") or "Non disponible",
            "priority": _pick("priority", "priority_level") or "normal",
            "owner": _pick("owner", "assignee", "life", "speaker") or default_owner,
            "blockage": _pick("blockage", "blocked_by", "blocker", "risk") or "aucun",
        }

    @app.get("/api/dashboard/work-items")
    def read_dashboard_work_items(current_life_only: bool = False) -> dict[str, object]:
        quests = read_quests()
        active = quests.get("active") if isinstance(quests.get("active"), list) else []
        completed = quests.get("completed") if isinstance(quests.get("completed"), list) else []

        quests_items = [
            _normalize_work_item(item, fallback_title="quête", default_owner="système")
            for item in [*active, *completed]
            if isinstance(item, dict)
        ]
        objectives_items = [
            _normalize_work_item(item, fallback_title="objectif", default_owner="système")
            for item in active
            if isinstance(item, dict)
        ]

        conversations_items: list[dict[str, str]] = []
        latest = _latest_run_file(current_life_only=current_life_only)
        if latest is not None:
            consciousness_path = _resolve_consciousness_path(
                latest.stem, current_life_only=current_life_only
            )
            if consciousness_path is not None:
                for line in consciousness_path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    try:
                        raw = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(raw, dict):
                        continue
                    enriched = dict(raw)
                    if "title" not in enriched:
                        enriched["title"] = raw.get("objective") or raw.get("summary") or "conversation"
                    if "status" not in enriched:
                        enriched["status"] = "success" if raw.get("success") is True else "in_progress"
                    conversations_items.append(
                        _normalize_work_item(
                            enriched,
                            fallback_title="conversation",
                            default_owner="agent",
                        )
                    )

        return {
            "quests": quests,
            "objectives": {"items": objectives_items},
            "conversations": {"run_id": latest.stem if latest is not None else None, "items": conversations_items},
        }

    @app.get("/ecosystem")
    def read_ecosystem(current_life_only: bool = False) -> dict:
        return _compute_ecosystem(current_life_only=current_life_only)

    @app.get("/alerts")
    def read_alerts(current_life_only: bool = False) -> dict[str, object]:
        latest = _latest_run_file(current_life_only=current_life_only)
        if latest is None:
            return {"run": None, "alerts": []}
        records = _read_jsonl_records(latest)
        return {"run": latest.stem, "alerts": alerts_from_records(records)}

    @app.get("/runs/latest")
    def read_latest_run(current_life_only: bool = False) -> dict[str, object]:
        latest = _latest_run_file(current_life_only=current_life_only)
        if latest is None:
            return {"run": None, "records": []}
        return {"run": latest.stem, "records": _read_jsonl_records(latest)}

    @app.get("/api/runs/{run_id}/timeline")
    def read_run_timeline(
        run_id: str,
        page: int = 1,
        page_size: int = 25,
        operator: str | None = None,
        decision: str | None = None,
        period_start: str | None = None,
        period_end: str | None = None,
        organism: str | None = None,
        current_life_only: bool = False,
    ) -> dict[str, object]:
        run_file = _resolve_run_file(run_id, current_life_only=current_life_only)
        if run_file is None:
            raise HTTPException(status_code=404, detail=f"run '{run_id}' not found")

        all_items: list[dict[str, object]] = []
        for record in _read_jsonl_records(run_file):
            item = _timeline_entry(record, run_id)
            if item is None:
                continue

            if operator and item.get("operator") != operator:
                continue
            if organism and item.get("organism") != organism:
                continue

            accepted = item.get("accepted")
            if decision == "accepted" and accepted is not True:
                continue
            if decision == "rejected" and accepted is not False:
                continue

            ts = _parse_ts(item.get("timestamp"))
            if (period_start or period_end) and ts is None:
                continue
            if period_start and ts is not None:
                start = _parse_ts(period_start)
                if start is not None and ts < start:
                    continue
            if period_end and ts is not None:
                end = _parse_ts(period_end)
                if end is not None and ts > end:
                    continue

            all_items.append(item)

        all_items.sort(key=lambda entry: str(entry.get("timestamp", "")))

        page = max(page, 1)
        page_size = min(max(page_size, 1), 200)
        total = len(all_items)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        items = all_items[start_idx:end_idx]

        return {
            "run_id": run_id,
            "filters": {
                "operator": operator,
                "decision": decision,
                "period_start": period_start,
                "period_end": period_end,
                "organism": organism,
            },
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": (total + page_size - 1) // page_size if total else 0,
            },
            "items": items,
        }

    @app.get("/api/lives/{life}/causal-timeline")
    def read_life_causal_timeline(
        life: str,
        limit: int = 100,
    ) -> dict[str, object]:
        life_dir = _resolve_life_dir(life)
        if life_dir is None:
            raise HTTPException(status_code=404, detail=f"life '{life}' not found")

        entries = read_causal_timeline(life_dir / "mem" / "causal_timeline.jsonl")
        entries = [entry for entry in entries if isinstance(entry, dict)]
        entries.sort(key=lambda item: str(item.get("ts", item.get("recorded_at", ""))))
        safe_limit = min(max(limit, 1), 500)
        items = entries[-safe_limit:]
        return {
            "life": life,
            "count": len(items),
            "items": items,
        }

    @app.get("/api/runs/{run_id}/consciousness")
    def read_run_consciousness(
        run_id: str,
        objective: str | None = None,
        mood: str | None = None,
        success: str | None = None,
        current_life_only: bool = False,
    ) -> dict[str, object]:
        consciousness_file = _resolve_consciousness_path(
            run_id, current_life_only=current_life_only
        )
        if consciousness_file is None:
            raise HTTPException(
                status_code=404, detail=f"consciousness timeline for run '{run_id}' not found"
            )

        success_filter: bool | None = None
        if isinstance(success, str):
            lowered = success.strip().lower()
            if lowered in {"true", "1", "yes", "success"}:
                success_filter = True
            elif lowered in {"false", "0", "no", "failure"}:
                success_filter = False

        items: list[dict[str, object]] = []
        for line in consciousness_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            if objective and record.get("objective") != objective:
                continue
            emotional = record.get("emotional_state")
            record_mood = emotional.get("mood") if isinstance(emotional, dict) else None
            if mood and record_mood != mood:
                continue
            if success_filter is not None and record.get("success") is not success_filter:
                continue
            items.append(record)

        items.sort(key=lambda item: str(item.get("ts", "")))
        return {
            "run_id": run_id,
            "filters": {"objective": objective, "mood": mood, "success": success},
            "count": len(items),
            "items": items,
        }

    @app.get("/api/runs/{run_id}/mutations/{index}")
    def read_run_mutation(
        run_id: str, index: int, current_life_only: bool = False
    ) -> dict[str, object]:
        run_file = _resolve_run_file(run_id, current_life_only=current_life_only)
        if run_file is None:
            raise HTTPException(status_code=404, detail=f"run '{run_id}' not found")

        mutations = [record for record in _read_jsonl_records(run_file) if _is_mutation_record(record)]
        if index < 0 or index >= len(mutations):
            raise HTTPException(
                status_code=404,
                detail=f"mutation index {index} out of bounds for run '{run_id}'",
            )
        return _mutation_detail(mutations[index], run_id=run_id, index=index)

    @app.get("/runs/latest/summary")
    def read_latest_run_summary(current_life_only: bool = False) -> dict[str, object]:
        latest = _latest_run_file(current_life_only=current_life_only)
        if latest is None:
            return {"run": None, "summary": None}

        records = _read_jsonl_records(latest)
        accepted = 0
        rejected = 0
        mutation_count = 0
        last_event: str | None = None
        last_timestamp: str | None = None
        for record in records:
            if _is_mutation_record(record):
                mutation_count += 1
            accepted_value = record.get("accepted")
            if not isinstance(accepted_value, bool):
                accepted_value = record.get("ok")
            if accepted_value is True:
                accepted += 1
            elif accepted_value is False:
                rejected += 1
            event = record.get("event")
            if isinstance(event, str):
                last_event = event
            ts = record.get("ts")
            if isinstance(ts, str):
                last_timestamp = ts

        return {
            "run": latest.stem,
            "summary": {
                "entries": len(records),
                "mutations": mutation_count,
                "accepted": accepted,
                "rejected": rejected,
                "last_event": last_event,
                "last_timestamp": last_timestamp,
            },
        }

    @app.get("/api/cockpit")
    def read_cockpit(current_life_only: bool = False) -> dict[str, object]:
        return _summarize_cockpit(current_life_only=current_life_only)

    @app.get("/api/cockpit/essential")
    def read_cockpit_essential(current_life_only: bool = False) -> dict[str, object]:
        return _summarize_cockpit_essential(current_life_only=current_life_only)

    @app.get("/dashboard/context")
    def read_dashboard_context() -> dict[str, object]:
        policy = load_runtime_policy()
        registry_state = _registry_overview()
        retention = retention_status_snapshot(base_dir=base_dir)
        return {
            "singular_root": str(registry_root),
            "singular_home": str(base_dir),
            "registry_lives_count": registry_state["lives_count"],
            "registry_state": {
                "active": registry_state["active"],
                "active_valid": registry_state["active_valid"],
                "is_empty": registry_state["is_empty"],
            },
            "onboarding": {
                "required": bool(registry_state["is_empty"]),
                "message": registry_state["onboarding_message"],
            },
            "policy": policy.to_payload(),
            "policy_impact": policy.impact_summary(),
            "skills_lifecycle": _skill_lifecycle_summary(),
            "retention": retention,
        }

    @app.get("/api/retention/status")
    def read_retention_status() -> dict[str, object]:
        payload = retention_status_snapshot(base_dir=base_dir)
        return dict(payload)

    @app.get("/timeline")
    def read_timeline(
        life: str | None = None,
        period: str | None = None,
        operator: str | None = None,
        decision: str | None = None,
        impact: str | None = None,
        current_life_only: bool = False,
    ) -> dict[str, object]:
        records = _load_run_records(current_life_only=current_life_only)
        items: list[dict[str, object]] = []

        for record in records:
            if not _is_mutation_record(record):
                continue
            rec_life = _record_life(record)
            rec_ts = record.get("ts")
            rec_operator = record.get("operator", record.get("op"))
            score_base = _as_float(record.get("score_base"))
            score_new = _as_float(record.get("score_new"))
            accepted = record.get("accepted")
            if not isinstance(accepted, bool):
                accepted = record.get("ok")
            if not isinstance(accepted, bool):
                accepted = None
            delta = None
            if score_base is not None and score_new is not None:
                delta = score_base - score_new
            rec_impact = "neutral"
            if delta is not None:
                if delta > 0:
                    rec_impact = "beneficial"
                elif delta < 0:
                    rec_impact = "risky"

            if life and rec_life != life:
                continue
            if operator and rec_operator != operator:
                continue
            if period and (not isinstance(rec_ts, str) or not rec_ts.startswith(period)):
                continue
            if decision == "accepted" and accepted is not True:
                continue
            if decision == "rejected" and accepted is not False:
                continue
            if impact and rec_impact != impact:
                continue

            items.append(
                {
                    "timestamp": rec_ts,
                    "life": rec_life,
                    "operator": rec_operator,
                    "accepted": accepted,
                    "impact": rec_impact,
                    "impact_delta": delta,
                    "score_base": score_base,
                    "score_new": score_new,
                    "run": record.get("_run_file"),
                }
            )

        items.sort(key=lambda item: str(item.get("timestamp", "")))
        return {
            "filters": {
                "life": life,
                "period": period,
                "operator": operator,
                "decision": decision,
                "impact": impact,
            },
            "count": len(items),
            "items": items,
        }

    def _life_trend_label(points: list[float]) -> str:
        return life_trend_label_service(points)

    def _life_trend_rank(trend: str) -> int:
        return life_trend_rank_service(trend)

    def _registry_life_meta(
        life_name: str, lives_payload: dict[str, object]
    ) -> tuple[str | None, dict[str, object] | None]:
        for slug, raw_meta in lives_payload.items():
            if not isinstance(slug, str):
                continue
            if isinstance(raw_meta, dict):
                candidate_name = raw_meta.get("name")
                if life_name == slug or (
                    isinstance(candidate_name, str) and candidate_name == life_name
                ):
                    return slug, raw_meta
            else:
                candidate_name = getattr(raw_meta, "name", None)
                if life_name == slug or (
                    isinstance(candidate_name, str) and candidate_name == life_name
                ):
                    return slug, None
        return None, None

    def _aggregate_lives(
        *,
        current_life_only: bool = False,
        compare_lives: set[str] | None = None,
        time_window: str = "all",
    ) -> tuple[dict[str, dict[str, object]], dict[str, object]]:
        return aggregate_lives_service(
            _load_run_records(current_life_only=current_life_only),
            registry=load_registry(),
            compare_lives=compare_lives,
            time_window=time_window,
            record_life=_record_life,
            record_run_id=_record_run_id,
            is_mutation_record=_is_mutation_record,
            as_float=_as_float,
            alerts_from_records=alerts_from_records,
            compute_vital_timeline=compute_vital_timeline,
            set_life_status=set_life_status,
            registry_life_meta=_registry_life_meta,
        )

    def _build_metrics_contract(
        comparison: dict[str, dict[str, object]]
    ) -> dict[str, object]:
        return build_metrics_contract_service(comparison)

    def _aggregate_code_evolution(life: str) -> dict[str, object]:
        return aggregate_code_evolution_service(
            _load_run_records(current_life_only=False),
            life=life,
            record_life=_record_life,
            record_run_id=_record_run_id,
            as_float=_as_float,
        )

    @app.get("/api/lives/{life}/code-evolution")
    def read_life_code_evolution(
        life: str,
        status: str | None = None,
        change_type: str | None = None,
        limit: int | None = None,
    ) -> dict[str, object]:
        payload = _aggregate_code_evolution(life)
        items = payload.get("items")
        if not isinstance(items, list):
            items = []

        normalized_status = status.strip().lower() if isinstance(status, str) else None
        normalized_change_type = (
            change_type.strip().lower() if isinstance(change_type, str) else None
        )
        filtered_items = [
            item
            for item in items
            if (
                normalized_status is None
                or str(item.get("status", "")).lower() == normalized_status
            )
            and (
                normalized_change_type is None
                or str(item.get("change_type", "")).lower() == normalized_change_type
            )
        ]
        if isinstance(limit, int) and limit >= 0:
            filtered_items = filtered_items[:limit]

        summary = payload.get("summary")
        if not isinstance(summary, dict):
            summary = {"by_status": {}, "by_change_type": {}, "by_target": {}}

        return {
            "life": life,
            "count": len(filtered_items),
            "items": filtered_items,
            "summary": summary,
            "filters": {
                "status": normalized_status,
                "change_type": normalized_change_type,
                "limit": limit,
            },
        }

    @app.get("/lives/comparison")
    def read_lives_comparison(
        sort_by: str = "score",
        sort_order: str = "desc",
        active_only: bool = False,
        degrading_only: bool = False,
        dead_only: bool = False,
        time_window: str = "all",
        compare_lives: str | None = None,
        current_life_only: bool = False,
    ) -> dict[str, object]:
        compare_set: set[str] | None = None
        if isinstance(compare_lives, str) and compare_lives.strip():
            compare_set = {
                part.strip()
                for part in compare_lives.split(",")
                if part.strip()
            }
        comparison, unattached = _aggregate_lives(
            current_life_only=current_life_only,
            compare_lives=compare_set,
            time_window=time_window,
        )
        metrics_contract = _build_metrics_contract(comparison)
        base_rows = [
            {
                "life": name,
                "code_evolution_endpoint": f"/api/lives/{name}/code-evolution",
                **payload,
            }
            for name, payload in comparison.items()
        ]
        lives_rows = list(base_rows)
        filter_steps: list[dict[str, object]] = [
            {
                "step": "before_filters",
                "label": "Vies avant filtres endpoint",
                "applied": True,
                "count": len(lives_rows),
            }
        ]

        if active_only:
            lives_rows = [
                row for row in lives_rows if row.get("is_registry_active_life") is True
            ]
        filter_steps.append(
            {
                "step": "active_only",
                "label": "Après filtre active_only",
                "applied": active_only,
                "count": len(lives_rows),
            }
        )
        if degrading_only:
            lives_rows = [row for row in lives_rows if row.get("trend") == "dégradation"]
        filter_steps.append(
            {
                "step": "degrading_only",
                "label": "Après filtre degrading_only",
                "applied": degrading_only,
                "count": len(lives_rows),
            }
        )
        if dead_only:
            lives_rows = [
                row for row in lives_rows if row.get("extinction_seen_in_runs") is True
            ]
        filter_steps.append(
            {
                "step": "dead_only",
                "label": "Après filtre dead_only",
                "applied": dead_only,
                "count": len(lives_rows),
            }
        )

        sort_key_map: dict[str, str] = {
            "life": "life",
            "score": "current_health_score",
            "trend": "trend_rank",
            "stability": "stability",
            "last_activity": "last_activity",
            "iterations": "iterations",
            "liveness": "life_liveness_index",
        }
        key_name = sort_key_map.get(sort_by, "current_health_score")
        reverse = sort_order != "asc"
        lives_rows.sort(
            key=lambda row: (
                row.get(key_name) is None,
                row.get(key_name),
                str(row.get("life", "")),
            ),
            reverse=reverse,
        )
        filter_steps.append(
            {
                "step": "sorted",
                "label": "Après tri",
                "applied": True,
                "count": len(lives_rows),
            }
        )

        registry_state = _registry_overview()
        return {
            "lives": comparison,
            "table": lives_rows,
            "life_metrics_contract": metrics_contract,
            "unattached_runs": unattached,
            "onboarding": {
                "required": bool(registry_state["is_empty"]),
                "message": registry_state["onboarding_message"],
            },
            "filters": {
                "sort_by": sort_by,
                "sort_order": "desc" if reverse else "asc",
                "active_only": active_only,
                "degrading_only": degrading_only,
                "dead_only": dead_only,
                "time_window": time_window,
                "compare_lives": sorted(compare_set) if compare_set else [],
            },
            "filter_diagnostics": {
                "before_filter_count": len(base_rows),
                "steps": filter_steps,
            },
        }

    @app.get("/lives/genealogy")
    def read_lives_genealogy(life: str | None = None) -> dict[str, object]:
        registry = load_registry()
        lives = registry.get("lives", {})
        active = registry.get("active")
        nodes: list[dict[str, object]] = []
        relationships: list[dict[str, object]] = []
        active_conflicts: list[dict[str, object]] = []
        if isinstance(life, str):
            life = life.strip() or None
        relation_updates: dict[tuple[str, str, str], datetime] = {}

        relations_journal = get_registry_root() / "mem" / "lives_relations.jsonl"
        if relations_journal.exists():
            for line in relations_journal.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                event = record.get("event")
                actor = record.get("actor")
                target = record.get("target")
                timestamp = _parse_iso8601(record.get("ts"))
                if not (
                    isinstance(event, str)
                    and isinstance(actor, str)
                    and actor
                    and isinstance(target, str)
                    and target
                    and timestamp is not None
                ):
                    continue
                pair = tuple(sorted((actor, target)))
                if event == "ally":
                    relation_updates[(pair[0], pair[1], "alliance")] = timestamp
                elif event in {"rival", "reconcile"}:
                    relation_updates[(pair[0], pair[1], "rivalry")] = timestamp

        def _relation_timestamp(source: str, target: str, relation_type: str) -> str | None:
            pair = tuple(sorted((source, target)))
            return _iso_or_none(relation_updates.get((pair[0], pair[1], relation_type)))

        def _relation_severity(*, relation_type: str, source_status: str, target_status: str, proximity: float) -> int:
            if relation_type == "rivalry":
                base = 2
                if source_status == "active" and target_status == "active":
                    base += 1
                if proximity >= 0.65:
                    base += 1
                return min(base, 4)
            if relation_type == "alliance":
                if source_status == "active" and target_status == "active":
                    return 1
                return 2
            return 1

        def _append_relationship(
            *,
            source: str,
            target: str,
            relation_type: str,
            source_status: str,
            target_status: str,
            source_proximity: float,
            active_relation: bool = True,
        ) -> None:
            severity = _relation_severity(
                relation_type=relation_type,
                source_status=source_status,
                target_status=target_status,
                proximity=source_proximity,
            )
            item = {
                "source": source,
                "target": target,
                "type": relation_type,
                "status": "active" if active_relation else "inactive",
                "updated_at": _relation_timestamp(source, target, relation_type),
                "severity": severity,
            }
            relationships.append(item)
            if relation_type == "rivalry" and active_relation:
                active_conflicts.append(
                    {
                        "life_a": min(source, target),
                        "life_b": max(source, target),
                        "type": relation_type,
                        "status": "active",
                        "updated_at": item["updated_at"],
                        "severity": severity,
                    }
                )

        if not isinstance(lives, dict):
            return {
                "active": active,
                "nodes": nodes,
                "edges": [],
                "social_edges": [],
                "relationships": relationships,
                "active_conflicts": active_conflicts,
                "active_relations": [],
                "filters": {"life": life},
                "onboarding": {"required": active is None, "message": "Aucune vie, créez-en une." if active is None else None},
            }

        statuses_by_slug: dict[str, str] = {}
        proximity_by_slug: dict[str, float] = {}
        for slug, meta in sorted(lives.items()):
            name = getattr(meta, "name", slug)
            status = getattr(meta, "status", "active")
            parents = getattr(meta, "parents", ()) or ()
            children = getattr(meta, "children", ()) or ()
            allies = getattr(meta, "allies", ()) or ()
            rivals = getattr(meta, "rivals", ()) or ()
            proximity_score = getattr(meta, "proximity_score", 0.5)
            lineage_depth = getattr(meta, "lineage_depth", 0)
            if not isinstance(parents, (tuple, list)):
                parents = ()
            if not isinstance(children, (tuple, list)):
                children = ()
            if not isinstance(allies, (tuple, list)):
                allies = ()
            if not isinstance(rivals, (tuple, list)):
                rivals = ()
            normalized_status = str(status).strip().lower() if isinstance(status, str) else "unknown"
            if normalized_status not in {"active", "extinct", "archived"}:
                normalized_status = "unknown"
            proximity_value = float(proximity_score) if isinstance(proximity_score, (int, float)) else 0.5
            proximity_value = max(0.0, min(1.0, proximity_value))
            statuses_by_slug[slug] = normalized_status
            proximity_by_slug[slug] = proximity_value
            nodes.append(
                {
                    "slug": slug,
                    "name": str(name),
                    "status": normalized_status,
                    "active": slug == active,
                    "lineage_depth": int(lineage_depth) if isinstance(lineage_depth, int) else 0,
                    "parents": [str(parent) for parent in parents if isinstance(parent, str)],
                    "children": [str(child) for child in children if isinstance(child, str)],
                    "allies": [str(ally) for ally in allies if isinstance(ally, str)],
                    "rivals": [str(rival) for rival in rivals if isinstance(rival, str)],
                    "proximity_score": proximity_value,
                }
            )

        known_lives = set(statuses_by_slug)
        unique_parent_edges: set[tuple[str, str]] = set()
        unique_alliance_edges: set[tuple[str, str]] = set()
        unique_rival_edges: set[tuple[str, str]] = set()
        for node in nodes:
            slug = str(node["slug"])
            source_status = statuses_by_slug.get(slug, "unknown")
            for parent in node.get("parents", []):
                if isinstance(parent, str) and parent and parent in known_lives:
                    edge_key = (parent, slug)
                    if edge_key in unique_parent_edges:
                        continue
                    unique_parent_edges.add(edge_key)
                    _append_relationship(
                        source=parent,
                        target=slug,
                        relation_type="parentage",
                        source_status=statuses_by_slug.get(parent, "unknown"),
                        target_status=source_status,
                        source_proximity=proximity_by_slug.get(parent, 0.5),
                    )

            for ally in node.get("allies", []):
                if not (isinstance(ally, str) and ally and ally in known_lives and ally != slug):
                    continue
                edge_key = tuple(sorted((slug, ally)))
                if edge_key in unique_alliance_edges:
                    continue
                unique_alliance_edges.add(edge_key)
                _append_relationship(
                    source=edge_key[0],
                    target=edge_key[1],
                    relation_type="alliance",
                    source_status=statuses_by_slug.get(edge_key[0], "unknown"),
                    target_status=statuses_by_slug.get(edge_key[1], "unknown"),
                    source_proximity=proximity_by_slug.get(edge_key[0], 0.5),
                )

            for rival in node.get("rivals", []):
                if not (isinstance(rival, str) and rival and rival in known_lives and rival != slug):
                    continue
                edge_key = tuple(sorted((slug, rival)))
                if edge_key in unique_rival_edges:
                    continue
                unique_rival_edges.add(edge_key)
                _append_relationship(
                    source=edge_key[0],
                    target=edge_key[1],
                    relation_type="rivalry",
                    source_status=statuses_by_slug.get(edge_key[0], "unknown"),
                    target_status=statuses_by_slug.get(edge_key[1], "unknown"),
                    source_proximity=proximity_by_slug.get(edge_key[0], 0.5),
                )

        unique_conflicts = {
            (
                item["life_a"],
                item["life_b"],
                item["type"],
                item["status"],
                item["updated_at"],
                item["severity"],
            )
            for item in active_conflicts
        }
        filtered_relations = [
            relation
            for relation in relationships
            if relation["status"] == "active"
            and (
                life is None
                or relation["source"] == life
                or relation["target"] == life
            )
        ]
        filtered_relations.sort(
            key=lambda item: (
                int(item.get("severity", 0)),
                _parse_iso8601(item.get("updated_at")) or datetime.fromtimestamp(0, timezone.utc),
                str(item.get("type", "")),
                str(item.get("source", "")),
                str(item.get("target", "")),
            ),
            reverse=True,
        )
        return {
            "active": active,
            "nodes": nodes,
            "edges": [
                {"parent": str(item["source"]), "child": str(item["target"])}
                for item in relationships
                if item.get("type") == "parentage"
            ],
            "social_edges": [
                {
                    "source": str(item["source"]),
                    "target": str(item["target"]),
                    "kind": "ally" if item.get("type") == "alliance" else "rival",
                }
                for item in relationships
                if item.get("type") in {"alliance", "rivalry"}
            ],
            "relationships": relationships,
            "active_relations": filtered_relations,
            "active_conflicts": [
                {
                    "life_a": a,
                    "life_b": b,
                    "type": relation_type,
                    "status": status,
                    "updated_at": updated_at,
                    "severity": severity,
                }
                for a, b, relation_type, status, updated_at, severity in sorted(unique_conflicts)
            ],
            "filters": {"life": life},
            "onboarding": {
                "required": not nodes and active is None,
                "message": "Aucune vie, créez-en une." if not nodes and active is None else None,
            },
        }

    @app.get("/mutations/top")
    def read_top_mutations(limit: int = 3, current_life_only: bool = False) -> dict[str, object]:
        mutations: list[dict[str, object]] = []
        operator_counts: Counter[str] = Counter()
        for record in _load_run_records(current_life_only=current_life_only):
            if not _is_mutation_record(record):
                continue
            operator = record.get("operator", record.get("op"))
            if isinstance(operator, str):
                operator_counts[operator] += 1
            score_base = _as_float(record.get("score_base"))
            score_new = _as_float(record.get("score_new"))
            delta = None
            if score_base is not None and score_new is not None:
                delta = score_base - score_new
            mutations.append(
                {
                    "timestamp": record.get("ts"),
                    "life": _record_life(record),
                    "operator": operator,
                    "accepted": record.get("accepted", record.get("ok")),
                    "impact_delta": delta,
                    "run": record.get("_run_file"),
                }
            )

        beneficial = sorted(
            mutations,
            key=lambda item: item["impact_delta"]
            if isinstance(item["impact_delta"], (int, float))
            else float("-inf"),
            reverse=True,
        )[:limit]
        risky = sorted(
            mutations,
            key=lambda item: item["impact_delta"]
            if isinstance(item["impact_delta"], (int, float))
            else float("inf"),
        )[:limit]
        frequent = [
            {"operator": operator, "count": count}
            for operator, count in operator_counts.most_common(limit)
        ]
        return {
            "most_beneficial": beneficial,
            "most_risky": risky,
            "most_frequent": frequent,
        }

    @app.get("/api/actions/{action}")
    def run_action(action: str, token: str | None = None, payload: str | None = None) -> dict[str, object]:
        try:
            actions.validate_token(token)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

        params: dict[str, object] = {}
        if payload:
            try:
                candidate = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=400, detail="payload must be valid JSON") from exc
            if not isinstance(candidate, dict):
                raise HTTPException(status_code=400, detail="payload must be an object")
            params = candidate

        result = actions.execute(action, params)
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=str(result.get("error") or "action failed"))
        return result

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        last_psyche_mtime_ns: int | None = None
        last_quests_mtime_ns: int | None = None
        log_cursors: dict[str, _LogCursor] = {}

        def _read_new_entries(file: Path, cursor: _LogCursor | None) -> tuple[list[str], _LogCursor]:
            stat = file.stat()
            inode = stat.st_ino
            next_cursor = cursor or _LogCursor(inode=inode, offset=0)
            if next_cursor.inode != inode or stat.st_size < next_cursor.offset:
                next_cursor = _LogCursor(inode=inode, offset=0)

            if stat.st_size <= next_cursor.offset:
                return [], next_cursor

            with file.open("r", encoding="utf-8") as handle:
                handle.seek(next_cursor.offset)
                chunk = handle.read()
                next_cursor.offset = handle.tell()
            entries = [line for line in chunk.splitlines() if line.strip()]
            return entries, next_cursor

        def _normalize_stream_event(file: Path, payload: dict[str, object]) -> dict[str, object] | None:
            event = _event_type(payload)
            if event is None:
                return None
            ts = payload.get("ts")
            return {
                "type": "run_event",
                "run_id": file.stem,
                "event": event,
                "ts": ts if isinstance(ts, str) else None,
            }

        try:
            while True:
                if psyche_path.exists():
                    mtime_ns = psyche_path.stat().st_mtime_ns
                    if mtime_ns != last_psyche_mtime_ns:
                        last_psyche_mtime_ns = mtime_ns
                        data = json.loads(psyche_path.read_text())
                        await ws.send_json({"type": "psyche", "data": data})

                if quests_path.exists():
                    mtime_ns = quests_path.stat().st_mtime_ns
                    if mtime_ns != last_quests_mtime_ns:
                        last_quests_mtime_ns = mtime_ns
                        data = json.loads(quests_path.read_text())
                        await ws.send_json({"type": "quests", "data": data})

                incremental_events: list[dict[str, object]] = []
                run_directories = _runs_dirs()
                if run_directories:
                    current_files: set[str] = set()
                    for directory in run_directories:
                        if not directory.exists():
                            continue
                        for file in directory.iterdir():
                            if not file.is_file() or file.suffix != ".jsonl":
                                continue
                            key = f"{directory.parent.name}/{file.name}"
                            current_files.add(key)
                            entries, next_cursor = await asyncio.to_thread(
                                _read_new_entries, file, log_cursors.get(key)
                            )
                            log_cursors[key] = next_cursor
                        for line in entries:
                            try:
                                payload = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            if not isinstance(payload, dict):
                                continue
                            event = _normalize_stream_event(file, payload)
                            if event is not None:
                                incremental_events.append(event)

                    for name in set(log_cursors) - current_files:
                        del log_cursors[name]
                else:
                    log_cursors.clear()

                for event in incremental_events:
                    await ws.send_json(event)
                await asyncio.sleep(0.1)
        except WebSocketDisconnect:
            pass

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _render_template("dashboard.html")

    @app.get("/runs/{run_id}/mutations/{index}", response_class=HTMLResponse)
    def mutation_detail_page(run_id: str, index: int) -> str:
        return _render_template(
            "mutation_detail.html",
            replacements={
                "__RUN_ID__": run_id,
                "__INDEX__": str(index),
                "__MUTATION_API_URL__": f"/api/runs/{run_id}/mutations/{index}",
            },
        )

    return app


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Launch the dashboard using Uvicorn."""
    try:
        import uvicorn
    except ImportError as exc:
        print(
            "Uvicorn is required to run the dashboard. Install it with 'pip install uvicorn'.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    app = create_app()
    uvicorn.run(app, host=host, port=port)
