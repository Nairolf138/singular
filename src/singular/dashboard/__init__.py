from __future__ import annotations

# mypy: ignore-errors

import asyncio
from collections import Counter
import json
from dataclasses import dataclass
from datetime import datetime
import os
import sys
from pathlib import Path
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from singular.schedulers.reevaluation import alerts_from_records


@dataclass
class _LogCursor:
    inode: int | None
    offset: int


def create_app(
    runs_dir: Path | str | None = None, psyche_file: Path | str | None = None
) -> FastAPI:
    """Create the dashboard FastAPI application."""
    base_dir = Path(os.environ.get("SINGULAR_HOME", "."))
    runs_path = Path(runs_dir) if runs_dir is not None else base_dir / "runs"
    psyche_path = (
        Path(psyche_file)
        if psyche_file is not None
        else base_dir / "mem" / "psyche.json"
    )
    app = FastAPI()

    def _load_run_records() -> list[dict[str, object]]:
        records: list[dict[str, object]] = []
        if not runs_path.exists():
            return records

        for file in runs_path.iterdir():
            if not file.is_file() or file.suffix != ".jsonl":
                continue
            for line in file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                if "_run_file" not in payload:
                    payload["_run_file"] = file.stem
                records.append(payload)
        return records

    def _is_mutation_record(record: dict[str, object]) -> bool:
        return any(
            field in record
            for field in ("score_base", "score_new", "ok", "accepted", "op", "operator")
        )

    def _as_float(value: object) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        return None

    def _record_life(record: dict[str, object]) -> str:
        skill = record.get("skill")
        if isinstance(skill, str) and ":" in skill:
            return skill.split(":", 1)[0]
        if isinstance(record.get("life"), str):
            return str(record["life"])
        run = record.get("_run_file")
        return str(run) if isinstance(run, str) else "default"

    def _compute_ecosystem() -> dict:
        organisms: dict[str, dict[str, object]] = {}
        if runs_path.exists():
            for file in runs_path.iterdir():
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
        return {
            "organisms": organisms,
            "summary": {
                "total_organisms": len(organisms),
                "alive_organisms": alive,
                "total_energy": total_energy,
                "total_resources": total_resources,
            },
        }

    def _iter_run_files() -> list[Path]:
        if not runs_path.exists():
            return []
        return sorted(
            [path for path in runs_path.iterdir() if path.is_file() and path.suffix == ".jsonl"],
            key=lambda path: (path.stat().st_mtime_ns, path.name),
        )

    def _read_jsonl_records(file: Path) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []
        for line in file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                records.append(payload)
        return records

    def _latest_run_file() -> Path | None:
        files = _iter_run_files()
        if not files:
            return None

        def _latest_ts_in_file(path: Path) -> str:
            latest_ts = ""
            for record in _read_jsonl_records(path):
                ts = record.get("ts")
                if isinstance(ts, str) and ts > latest_ts:
                    latest_ts = ts
            return latest_ts

        return max(
            files,
            key=lambda path: (path.stat().st_mtime_ns, _latest_ts_in_file(path), path.name),
        )

    def _parse_ts(value: object) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

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

    def _summarize_cockpit() -> dict[str, object]:
        latest = _latest_run_file()
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
        }


    @app.get("/logs")
    def read_logs() -> dict[str, str]:
        logs: dict[str, str] = {}
        if runs_path.exists():
            for file in runs_path.iterdir():
                if file.is_file():
                    logs[file.name] = file.read_text()
        return logs

    @app.get("/psyche")
    def read_psyche() -> dict:
        if not psyche_path.exists():
            raise HTTPException(status_code=404, detail="psyche.json not found")
        return json.loads(psyche_path.read_text())

    @app.get("/ecosystem")
    def read_ecosystem() -> dict:
        return _compute_ecosystem()

    @app.get("/alerts")
    def read_alerts() -> dict[str, object]:
        latest = _latest_run_file()
        if latest is None:
            return {"run": None, "alerts": []}
        records = _read_jsonl_records(latest)
        return {"run": latest.stem, "alerts": alerts_from_records(records)}

    @app.get("/runs/latest")
    def read_latest_run() -> dict[str, object]:
        latest = _latest_run_file()
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
    ) -> dict[str, object]:
        run_file = runs_path / f"{run_id}.jsonl"
        if not run_file.exists():
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

    @app.get("/runs/latest/summary")
    def read_latest_run_summary() -> dict[str, object]:
        latest = _latest_run_file()
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
    def read_cockpit() -> dict[str, object]:
        return _summarize_cockpit()

    @app.get("/timeline")
    def read_timeline(
        life: str | None = None,
        period: str | None = None,
        operator: str | None = None,
        decision: str | None = None,
        impact: str | None = None,
    ) -> dict[str, object]:
        records = _load_run_records()
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

    @app.get("/lives/comparison")
    def read_lives_comparison() -> dict[str, object]:
        by_life: dict[str, list[dict[str, object]]] = {}
        for record in _load_run_records():
            if _is_mutation_record(record):
                by_life.setdefault(_record_life(record), []).append(record)

        comparison: dict[str, dict[str, float | int | None]] = {}
        for life_name, records in by_life.items():
            records = sorted(records, key=lambda rec: str(rec.get("ts", "")))
            score_points = [
                (
                    _as_float(rec.get("score_base")),
                    _as_float(rec.get("score_new")),
                )
                for rec in records
            ]
            health_values = []
            for rec in records:
                health = rec.get("health")
                if isinstance(health, dict):
                    health_values.append(_as_float(health.get("score")))
            health_values = [value for value in health_values if value is not None]
            ms_points = [_as_float(rec.get("ms_new")) for rec in records]
            ms_points = [value for value in ms_points if value is not None]
            accepted_values: list[bool] = []
            for rec in records:
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
            if first_base is not None and last_new is not None and len(records) > 1:
                progression_slope = (first_base - last_new) / (len(records) - 1)

            failure_rate = None
            if accepted_values:
                failures = sum(1 for value in accepted_values if not value)
                failure_rate = failures / len(accepted_values)

            evolution_speed = None
            if ms_points:
                evolution_speed = sum(ms_points) / len(ms_points)

            comparison[life_name] = {
                "health_score": (
                    sum(health_values) / len(health_values) if health_values else None
                ),
                "progression_slope": progression_slope,
                "failure_rate": failure_rate,
                "evolution_speed": evolution_speed,
                "mutations": len(records),
            }

        return {"lives": comparison}

    @app.get("/mutations/top")
    def read_top_mutations(limit: int = 3) -> dict[str, object]:
        mutations: list[dict[str, object]] = []
        operator_counts: Counter[str] = Counter()
        for record in _load_run_records():
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

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        last_psyche_mtime_ns: int | None = None
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

        try:
            while True:
                if psyche_path.exists():
                    mtime_ns = psyche_path.stat().st_mtime_ns
                    if mtime_ns != last_psyche_mtime_ns:
                        last_psyche_mtime_ns = mtime_ns
                        data = json.loads(psyche_path.read_text())
                        await ws.send_json({"type": "psyche", "data": data})

                incremental_logs: dict[str, list[str]] = {}
                if runs_path.exists():
                    current_files: set[str] = set()
                    for file in runs_path.iterdir():
                        if not file.is_file():
                            continue
                        current_files.add(file.name)
                        entries, next_cursor = await asyncio.to_thread(
                            _read_new_entries, file, log_cursors.get(file.name)
                        )
                        log_cursors[file.name] = next_cursor
                        if entries:
                            incremental_logs[file.name] = entries

                    for name in set(log_cursors) - current_files:
                        del log_cursors[name]
                else:
                    log_cursors.clear()

                if incremental_logs:
                    await ws.send_json({"type": "logs", "data": incremental_logs})
                await asyncio.sleep(0.1)
        except WebSocketDisconnect:
            pass

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (
            "<html><head><title>Singular Dashboard</title></head><body>"
            "<h1>Singular Dashboard</h1>"
            "<section><h2>Cockpit</h2>"
            "<div id='cockpit-status'></div>"
            "<div style='display:grid;grid-template-columns:repeat(2,minmax(240px,1fr));gap:12px;'>"
            "<div><h3>Score santé</h3><pre id='kpi-health'></pre></div>"
            "<div><h3>Tendance</h3><pre id='kpi-trend'></pre></div>"
            "<div><h3>Taux mutations acceptées</h3><pre id='kpi-accepted'></pre></div>"
            "<div><h3>Alertes critiques</h3><pre id='kpi-alerts'></pre></div>"
            "</div>"
            "<h3>Dernière mutation notable</h3><pre id='kpi-notable'></pre>"
            "<h3>Prochaine action recommandée</h3><pre id='kpi-next-action'></pre>"
            "<h3>Actions suggérées</h3><pre id='kpi-actions'></pre>"
            "</section>"
            "<h2>Psyche</h2><pre id='psyche'></pre>"
            "<h2>Ecosystem Summary</h2><pre id='ecosystem-summary'></pre>"
            "<h2>Organisms</h2><pre id='organisms'></pre>"
            "<h2>Frise des événements</h2>"
            "<div id='timeline' style='display:flex;gap:8px;overflow:auto;white-space:nowrap;'></div>"
            "<h3>Détail événement</h3><pre id='timeline-detail'>Cliquez sur un événement.</pre>"
            "<h2>Runs</h2><div id='logs'></div>"
            "<script>const ws=new WebSocket(`ws://${location.host}/ws`);"
            "const loadEco=()=>fetch('/ecosystem').then(r=>r.json()).then(d=>{document.getElementById('ecosystem-summary').textContent=JSON.stringify(d.summary,null,2);document.getElementById('organisms').textContent=JSON.stringify(d.organisms,null,2);});"
            "const loadCockpit=()=>fetch('/api/cockpit').then(r=>r.json()).then(d=>{"
            "document.getElementById('cockpit-status').textContent=`Statut global: ${d.global_status}`;"
            "document.getElementById('kpi-health').textContent=d.health_score===null?'n/a':String(d.health_score);"
            "document.getElementById('kpi-trend').textContent=d.trend;"
            "document.getElementById('kpi-accepted').textContent=d.accepted_mutation_rate===null?'n/a':`${(d.accepted_mutation_rate*100).toFixed(1)}%`;"
            "document.getElementById('kpi-alerts').textContent=d.critical_alerts.length?JSON.stringify(d.critical_alerts,null,2):'Aucune alerte critique';"
            "document.getElementById('kpi-notable').textContent=d.last_notable_mutation?JSON.stringify(d.last_notable_mutation,null,2):'Aucune mutation notable';"
            "document.getElementById('kpi-next-action').textContent=d.next_action;"
            "document.getElementById('kpi-actions').textContent=JSON.stringify(d.suggested_actions,null,2);"
            "});"
            "const loadTimeline=()=>fetch('/runs/latest').then(r=>r.json()).then(meta=>{if(!meta.run){return {items:[]};}return fetch(`/api/runs/${meta.run}/timeline?page=1&page_size=120`).then(r=>r.json());}).then(data=>{const wrap=document.getElementById('timeline');const detail=document.getElementById('timeline-detail');wrap.innerHTML='';for(const item of data.items||[]){const btn=document.createElement('button');btn.textContent=`${item.event} · ${item.timestamp||'n/a'}`;btn.style.padding='6px';btn.onclick=()=>{detail.textContent=JSON.stringify({event:item.event,timestamp:item.timestamp,summary:item.human_summary,decision_reason:item.decision_reason,score_before:item.score_before,score_after:item.score_after,diff:item.diff,loop_modifications:item.loop_modifications},null,2);};wrap.appendChild(btn);}if(!(data.items||[]).length){detail.textContent='Aucun événement de frise disponible.';}});"
            "loadEco();loadCockpit();loadTimeline();setInterval(()=>{loadEco();loadCockpit();loadTimeline();},500);"
            "ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.type==='psyche'){document.getElementById('psyche').textContent=JSON.stringify(m.data,null,2);}else if(m.type==='logs'){const d=document.getElementById('logs');for(const [n,entries] of Object.entries(m.data)){let pre=document.getElementById(`log-${n}`);if(!pre){pre=document.createElement('pre');pre.id=`log-${n}`;pre.textContent=n+'\n';d.appendChild(pre);}for(const entry of entries){pre.textContent+=entry+'\n';}}}};"
            "</script></body></html>"
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
