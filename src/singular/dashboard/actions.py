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
        return {
            "registry_root": str(self.root),
            "current_life_home": str(current_home),
            "vital_metrics": vital_metrics,
        }

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
        provider = params.get("provider")
        if provider is not None:
            provider = self._require_non_empty_text(provider, field="provider", max_len=40)
        seed = params.get("seed")
        if seed is not None and not isinstance(seed, int):
            raise ValueError("seed must be an integer")

        from singular.lives import resolve_life
        from singular.organisms.talk import talk

        life = resolve_life(None)
        if life is None:
            raise ValueError("no active life")
        os.environ["SINGULAR_HOME"] = str(life)

        def _run() -> dict[str, Any]:
            talk(provider=provider, seed=seed, prompt=prompt)
            return {"life": str(life), "prompt": prompt}

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
