from __future__ import annotations

import io
import json
import os
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


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
        self.root = Path(root or os.environ.get("SINGULAR_ROOT", Path.home() / ".singular"))
        self.home = Path(home or os.environ.get("SINGULAR_HOME", "."))

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
            else:
                return ActionResult(
                    ok=False,
                    action=action,
                    data={},
                    log="",
                    error=f"unsupported action: {action}",
                ).to_payload()
            return result.to_payload()
        except Exception as exc:  # pragma: no cover - defensive fallback
            return ActionResult(
                ok=False,
                action=action,
                data={},
                log="",
                error=str(exc),
            ).to_payload()

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
