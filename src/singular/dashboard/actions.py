from __future__ import annotations

import io
import json
import os
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from singular.lives import get_registry_root
from singular.sensors import load_host_sensor_thresholds
from singular.skills_daily import build_daily_skills_snapshot


@dataclass(slots=True)
class ActionResult:
    ok: bool
    action: str
    data: dict[str, Any]
    log: str
    error: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "action": self.action,
            "data": self.data,
            "log": self.log,
            "error": self.error,
        }


class DashboardActionService:
    """Execute controlled dashboard actions with strict validation."""

    def __init__(self, *, root: Path | None = None, home: Path | None = None) -> None:
        self.root = Path(root) if root is not None else get_registry_root()
        if home is not None:
            self.home = Path(home)
        else:
            self.home = Path(os.environ.get("SINGULAR_HOME", self.root))

    def _context_payload(self) -> dict[str, Any]:
        current_home = Path(os.environ.get("SINGULAR_HOME", str(self.home)))
        runs_dir = current_home / "runs"
        vital_metrics = self._consolidated_vital_metrics(runs_dir=runs_dir)
        host_metrics = self._consolidated_host_metrics(runs_dir=runs_dir)
        daily_skills = build_daily_skills_snapshot(self._read_run_records(runs_dir=runs_dir))
        return {
            "registry_root": str(self.root),
            "current_life_home": str(current_home),
            "vital_metrics": vital_metrics,
            "host_metrics": host_metrics,
            "daily_skills": daily_skills,
        }

    def _read_run_records(self, *, runs_dir: Path) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        if not runs_dir.exists():
            return records
        for file in runs_dir.iterdir():
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
                if isinstance(payload, dict):
                    records.append(payload)
        return records

    def _consolidated_vital_metrics(self, *, runs_dir: Path) -> dict[str, Any]:
        if not runs_dir.exists():
            return {
                "health_score": None,
                "accepted_mutation_rate": None,
                "circadian_phase": "indéterminée",
                "risk_level": "n/a",
            }
        latest_file: Path | None = None
        latest_mtime = -1
        for file in runs_dir.iterdir():
            if not file.is_file() or file.suffix != ".jsonl":
                continue
            mtime = file.stat().st_mtime_ns
            if mtime > latest_mtime:
                latest_file = file
                latest_mtime = mtime
        if latest_file is None:
            return {
                "health_score": None,
                "accepted_mutation_rate": None,
                "circadian_phase": "indéterminée",
                "risk_level": "n/a",
            }
        records: list[dict[str, Any]] = []
        for line in latest_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                records.append(payload)
        accepted_values: list[bool] = []
        health_scores: list[float] = []
        for record in records:
            accepted = record.get("accepted")
            if not isinstance(accepted, bool):
                accepted = record.get("ok")
            if isinstance(accepted, bool):
                accepted_values.append(accepted)
            health = record.get("health")
            if isinstance(health, dict):
                score = health.get("score")
                if isinstance(score, (int, float)):
                    health_scores.append(float(score))
        accepted_rate = (
            sum(1 for value in accepted_values if value) / len(accepted_values)
            if accepted_values
            else None
        )
        risk_level = "faible"
        if accepted_rate is not None and accepted_rate < 0.5:
            risk_level = "élevé"
        elif accepted_rate is None:
            risk_level = "n/a"
        hour_utc = datetime.now(timezone.utc).hour
        if 5 <= hour_utc < 12:
            circadian_phase = "matin"
        elif 12 <= hour_utc < 18:
            circadian_phase = "jour"
        elif 18 <= hour_utc < 23:
            circadian_phase = "soir"
        else:
            circadian_phase = "nuit"
        return {
            "health_score": health_scores[-1] if health_scores else None,
            "accepted_mutation_rate": accepted_rate,
            "circadian_phase": circadian_phase,
            "risk_level": risk_level,
        }

    @staticmethod
    def _host_metric_risk(
        metric: str,
        value: float | None,
        thresholds: Any,
    ) -> str:
        if value is None:
            return "unsupported"
        if metric == "cpu":
            if value >= float(thresholds.cpu_critical_percent):
                return "critical"
            if value >= float(thresholds.cpu_warning_percent):
                return "warn"
            return "ok"
        if metric == "ram":
            if value >= float(thresholds.ram_critical_percent):
                return "critical"
            if value >= float(thresholds.ram_warning_percent):
                return "warn"
            return "ok"
        if metric == "temperature":
            if value >= float(thresholds.temperature_critical_c):
                return "critical"
            if value >= float(thresholds.temperature_warning_c):
                return "warn"
            return "ok"
        if metric == "disk":
            if value >= float(thresholds.disk_critical_percent):
                return "critical"
            return "ok"
        return "unsupported"

    @staticmethod
    def _extract_host_metrics(record: dict[str, Any]) -> dict[str, Any] | None:
        host_metrics = record.get("host_metrics")
        if isinstance(host_metrics, dict):
            return host_metrics
        signals = record.get("signals")
        if isinstance(signals, dict):
            candidate = signals.get("host_metrics")
            if isinstance(candidate, dict):
                return candidate
        payload = record.get("payload")
        if isinstance(payload, dict):
            candidate = payload.get("host_metrics")
            if isinstance(candidate, dict):
                return candidate
        return None

    def _consolidated_host_metrics(self, *, runs_dir: Path) -> dict[str, Any]:
        thresholds = load_host_sensor_thresholds()
        records = self._read_run_records(runs_dir=runs_dir)
        recent = records[-120:]
        history_map: dict[str, list[dict[str, Any]]] = {"cpu": [], "ram": [], "temperature": [], "disk": []}
        latest_values: dict[str, float | None] = {"cpu": None, "ram": None, "temperature": None, "disk": None}
        latest_statuses: dict[str, dict[str, Any] | None] = {"cpu": None, "ram": None, "temperature": None, "disk": None}
        latest_adaptation: dict[str, Any] | None = None
        for record in recent:
            ts = record.get("ts")
            host_metrics = self._extract_host_metrics(record)
            if isinstance(host_metrics, dict):
                metric_map = {
                    "cpu": host_metrics.get("cpu_percent"),
                    "ram": host_metrics.get("ram_used_percent"),
                    "temperature": host_metrics.get("host_temperature_c"),
                    "disk": host_metrics.get("disk_used_percent"),
                }
                metric_status_map = (
                    host_metrics.get("metric_status") if isinstance(host_metrics.get("metric_status"), dict) else {}
                )
                metric_status_aliases = {
                    "cpu": "cpu_percent",
                    "ram": "ram_used_percent",
                    "temperature": "host_temperature_c",
                    "disk": "disk_used_percent",
                }
                for metric_name, raw_value in metric_map.items():
                    status_payload = metric_status_map.get(metric_status_aliases[metric_name], {})
                    if isinstance(status_payload, dict):
                        latest_statuses[metric_name] = status_payload
                        raw_value = status_payload.get("value", raw_value)
                    if isinstance(raw_value, (int, float)):
                        value = float(raw_value)
                        latest_values[metric_name] = value
                        history_map[metric_name].append(
                            {
                                "ts": ts if isinstance(ts, str) else None,
                                "value": value,
                                "risk": self._host_metric_risk(metric_name, value, thresholds),
                            }
                        )
            event = record.get("event")
            adaptation_payload: dict[str, Any] | None = None
            if event == "orchestrator.adaptation" and isinstance(record.get("payload"), dict):
                adaptation_payload = record["payload"]
            elif isinstance(record.get("adaptation"), dict):
                adaptation_payload = record["adaptation"]
            if isinstance(adaptation_payload, dict):
                latest_adaptation = {
                    "ts": ts if isinstance(ts, str) else None,
                    "triggered_rules": adaptation_payload.get("triggered_rules", []),
                    "cpu_budget_percent": adaptation_payload.get("cpu_budget_percent"),
                    "skip_action_tick": bool(adaptation_payload.get("skip_action_tick", False)),
                    "safe_mode": adaptation_payload.get("safe_mode"),
                }

        metrics_payload: dict[str, dict[str, Any]] = {}
        risk_priority = {"unsupported": -1, "ok": 0, "warn": 1, "critical": 2}
        global_status = "ok"
        for metric_name in ("cpu", "ram", "temperature", "disk"):
            value = latest_values[metric_name]
            status_payload = latest_statuses.get(metric_name) if isinstance(latest_statuses.get(metric_name), dict) else {}
            status = str((status_payload or {}).get("status") or ("available" if value is not None else "unsupported"))
            reason = (status_payload or {}).get("reason")
            last_seen_at = (status_payload or {}).get("last_seen_at")
            unit = (status_payload or {}).get("unit")
            risk = self._host_metric_risk(metric_name, value, thresholds) if status != "unsupported" else "unsupported"
            trend_history = history_map[metric_name][-8:]
            metrics_payload[metric_name] = {
                "value": value,
                "unit": unit,
                "status": status,
                "reason": reason,
                "last_seen_at": last_seen_at,
                "risk": risk,
                "history": trend_history,
            }
            if risk_priority.get(risk, -1) > risk_priority.get(global_status, 0):
                global_status = risk
        if all(metrics_payload[name]["status"] == "unsupported" for name in metrics_payload):
            global_status = "unsupported"

        return {
            "global_status": global_status,
            "metrics": metrics_payload,
            "latest_sensor_adaptation": latest_adaptation,
        }

    def validate_token(self, token: str | None) -> None:
        expected = os.environ.get("SINGULAR_DASHBOARD_ACTION_TOKEN")
        if expected and token != expected:
            raise PermissionError("invalid action token")

    def execute(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            if action == "birth":
                result = self._birth(params)
            elif action == "talk":
                result = self._talk(params)
            elif action == "loop":
                result = self._loop(params)
            elif action == "report":
                result = self._report(params)
            elif action == "lives_list":
                result = self._lives_list(params)
            elif action == "lives_use":
                result = self._lives_use(params)
            elif action == "archive":
                result = self._archive(params)
            elif action == "memorial":
                result = self._memorial(params)
            elif action == "clone":
                result = self._clone(params)
            elif action == "emergency_stop":
                result = self._emergency_stop(params)
            else:
                payload = ActionResult(
                    ok=False,
                    action=action,
                    data=self._context_payload(),
                    log="",
                    error=f"unsupported action: {action}",
                ).to_payload()
                return payload
            payload = result.to_payload()
            payload["context"] = self._context_payload()
            return payload
        except Exception as exc:  # pragma: no cover - defensive fallback
            payload = ActionResult(
                ok=False,
                action=action,
                data=self._context_payload(),
                log="",
                error=str(exc),
            ).to_payload()
            payload["context"] = self._context_payload()
            return payload

    def _capture(self, fn: Callable[[], dict[str, Any]]) -> tuple[dict[str, Any], str]:
        stream = io.StringIO()
        with redirect_stdout(stream):
            data = fn()
        log = stream.getvalue().strip()
        if len(log) > 1200:
            log = f"{log[:1200]}..."
        return data, log

    @staticmethod
    def _require_non_empty_text(value: Any, *, field: str, max_len: int) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{field} must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{field} cannot be empty")
        if len(normalized) > max_len:
            raise ValueError(f"{field} too long (max {max_len})")
        return normalized

    @staticmethod
    def _require_float(value: Any, *, field: str, min_value: float, max_value: float) -> float:
        if not isinstance(value, (int, float)):
            raise ValueError(f"{field} must be a number")
        float_value = float(value)
        if float_value < min_value or float_value > max_value:
            raise ValueError(f"{field} must be between {min_value} and {max_value}")
        return float_value

    def _birth(self, params: dict[str, Any]) -> ActionResult:
        name = self._require_non_empty_text(params.get("name", "New life"), field="name", max_len=80)
        seed = params.get("seed")
        if seed is not None and not isinstance(seed, int):
            raise ValueError("seed must be an integer")

        from singular.lives import bootstrap_life

        def _run() -> dict[str, Any]:
            meta = bootstrap_life(name, seed=seed)
            os.environ["SINGULAR_HOME"] = str(meta.path)
            return {
                "name": meta.name,
                "slug": meta.slug,
                "path": str(meta.path),
            }

        data, log = self._capture(_run)
        return ActionResult(ok=True, action="birth", data=data, log=log)

    def _talk(self, params: dict[str, Any]) -> ActionResult:
        prompt = self._require_non_empty_text(params.get("prompt"), field="prompt", max_len=400)
        name = params.get("name")
        if name is not None:
            name = self._require_non_empty_text(name, field="name", max_len=80)
        provider = params.get("provider")
        if provider is not None:
            provider = self._require_non_empty_text(provider, field="provider", max_len=40)
        seed = params.get("seed")
        if seed is not None and not isinstance(seed, int):
            raise ValueError("seed must be an integer")

        from singular.lives import resolve_life
        from singular.organisms.talk import talk

        life = resolve_life(name)
        if life is None:
            raise ValueError(f"unknown life: {name}" if name else "no active life")
        os.environ["SINGULAR_HOME"] = str(life)

        def _run() -> dict[str, Any]:
            talk(provider=provider, seed=seed, prompt=prompt)
            return {"life": str(life), "name": name, "prompt": prompt}

        data, log = self._capture(_run)
        return ActionResult(ok=True, action="talk", data=data, log=log)

    def _loop(self, params: dict[str, Any]) -> ActionResult:
        budget = self._require_float(
            params.get("budget_seconds"), field="budget_seconds", min_value=0.1, max_value=3600.0
        )
        run_id = self._require_non_empty_text(params.get("run_id", "loop"), field="run_id", max_len=64)
        seed = params.get("seed")
        if seed is not None and not isinstance(seed, int):
            raise ValueError("seed must be an integer")

        from singular.lives import resolve_life
        from singular.runs.loop import loop

        life = resolve_life(None)
        if life is None:
            raise ValueError("no active life")
        os.environ["SINGULAR_HOME"] = str(life)
        checkpoint = Path(life) / "life_checkpoint.json"
        skills_dir = Path(life) / "skills"

        def _run() -> dict[str, Any]:
            loop(
                skills_dir=skills_dir,
                checkpoint=checkpoint,
                budget_seconds=budget,
                run_id=run_id,
                seed=seed,
            )
            return {"run_id": run_id, "budget_seconds": budget}

        data, log = self._capture(_run)
        return ActionResult(ok=True, action="loop", data=data, log=log)

    def _report(self, params: dict[str, Any]) -> ActionResult:
        run_id = params.get("run_id")
        if run_id is not None:
            run_id = self._require_non_empty_text(run_id, field="run_id", max_len=120)

        from singular.cli import _resolve_latest_run_id
        from singular.runs.report import report

        if run_id is None:
            run_id = _resolve_latest_run_id()
        if run_id is None:
            raise ValueError("no run available")

        def _run() -> dict[str, Any]:
            report(run_id=run_id, output_format="json")
            return {"run_id": run_id}

        data, log = self._capture(_run)
        parsed: dict[str, Any] | None = None
        try:
            parsed = json.loads(log)
        except json.JSONDecodeError:
            parsed = None
        if parsed is not None:
            data["report"] = parsed
        return ActionResult(ok=True, action="report", data=data, log=log)

    def _lives_list(self, params: dict[str, Any]) -> ActionResult:
        if params:
            raise ValueError("lives_list does not accept parameters")
        from singular.lives import load_registry

        def _run() -> dict[str, Any]:
            registry = load_registry()
            active = registry.get("active")
            items = []
            for slug, meta in sorted(registry.get("lives", {}).items()):
                items.append(
                    {
                        "slug": slug,
                        "name": meta.name,
                        "path": str(meta.path),
                        "active": slug == active,
                        "parents": list(meta.parents),
                        "lineage_depth": meta.lineage_depth,
                    }
                )
            return {"active": active, "lives": items}

        data, log = self._capture(_run)
        return ActionResult(ok=True, action="lives_list", data=data, log=log)

    def _lives_use(self, params: dict[str, Any]) -> ActionResult:
        name = self._require_non_empty_text(params.get("name"), field="name", max_len=80)
        from singular.lives import resolve_life

        def _run() -> dict[str, Any]:
            life = resolve_life(name)
            if life is None:
                raise ValueError(f"unknown life: {name}")
            os.environ["SINGULAR_HOME"] = str(life)
            return {"name": name, "path": str(life)}

        data, log = self._capture(_run)
        return ActionResult(ok=True, action="lives_use", data=data, log=log)

    def _archive(self, params: dict[str, Any]) -> ActionResult:
        name = self._require_non_empty_text(params.get("name"), field="name", max_len=80)
        from singular.lives import archive_life

        def _run() -> dict[str, Any]:
            meta = archive_life(name)
            return {
                "name": meta.name,
                "slug": meta.slug,
                "status": meta.status,
                "guided_message": "Vie archivée: statut extinct, prête pour memorial.",
            }

        data, log = self._capture(_run)
        return ActionResult(ok=True, action="archive", data=data, log=log)

    def _emergency_stop(self, params: dict[str, Any]) -> ActionResult:
        scope = params.get("scope", "active_life")
        if scope != "active_life":
            raise ValueError("emergency_stop only supports scope=active_life")

        from singular.lives import load_registry, resolve_life

        life = resolve_life(None)
        if life is None:
            raise ValueError("no active life")
        registry = load_registry()
        active = registry.get("active")
        lives = registry.get("lives") if isinstance(registry.get("lives"), dict) else {}
        metadata = lives.get(active) if isinstance(active, str) else None
        mem_dir = Path(life) / "mem"
        stop_path = mem_dir / "orchestrator.stop.json"
        requested_at = datetime.now(timezone.utc).isoformat()

        def _run() -> dict[str, Any]:
            mem_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "stop": True,
                "reason": "dashboard_emergency_stop",
                "requested_at": requested_at,
                "requested_by": "dashboard",
                "scope": scope,
                "life": active,
            }
            stop_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return {
                "life": active,
                "name": getattr(metadata, "name", active),
                "path": str(life),
                "stop_signal_path": str(stop_path),
                "requested_at": requested_at,
                "guided_message": "Arrêt d’urgence demandé: le signal d’arrêt sera honoré par l’orchestrateur actif.",
            }

        data, log = self._capture(_run)
        return ActionResult(ok=True, action="emergency_stop", data=data, log=log)

    def _memorial(self, params: dict[str, Any]) -> ActionResult:
        name = self._require_non_empty_text(params.get("name"), field="name", max_len=80)
        message = self._require_non_empty_text(
            params.get("message", "Merci pour ce cycle de vie."),
            field="message",
            max_len=500,
        )
        from singular.lives import memorialize_life

        def _run() -> dict[str, Any]:
            path = memorialize_life(name, message=message)
            return {
                "name": name,
                "memorial_path": str(path),
                "guided_message": "Mémorial créé. Vous pouvez maintenant cloner cette vie.",
            }

        data, log = self._capture(_run)
        return ActionResult(ok=True, action="memorial", data=data, log=log)

    def _clone(self, params: dict[str, Any]) -> ActionResult:
        name = self._require_non_empty_text(params.get("name"), field="name", max_len=80)
        new_name = params.get("new_name")
        if new_name is not None:
            new_name = self._require_non_empty_text(new_name, field="new_name", max_len=80)
        from singular.lives import clone_life

        def _run() -> dict[str, Any]:
            meta = clone_life(name, new_name=new_name)
            os.environ["SINGULAR_HOME"] = str(meta.path)
            return {
                "source": name,
                "name": meta.name,
                "slug": meta.slug,
                "path": str(meta.path),
                "guided_message": "Clone actif. Recommandé: lancer `status` puis `loop`.",
            }

        data, log = self._capture(_run)
        return ActionResult(ok=True, action="clone", data=data, log=log)
