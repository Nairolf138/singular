"""Periodic routines orchestration and state persistence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping

from singular.memory import _atomic_write_text

DEFAULT_ROUTINES_PATH = Path(__file__).resolve().parents[2] / "configs" / "routines.yaml"


@dataclass(frozen=True)
class RoutineSpec:
    """Static routine configuration loaded from YAML."""

    id: str
    prompt: str
    description: str
    interval_minutes: int = 60
    priority: int = 50
    max_risk: float = 1.0


@dataclass
class RoutineTask:
    """One due routine execution task."""

    id: str
    prompt: str
    description: str
    priority: int
    due_at: str
    deadline_at: str
    max_risk: float


@dataclass
class RoutineRunState:
    """Persisted execution state for a routine."""

    last_run_at: str | None = None
    last_success: bool | None = None
    last_latency_ms: float | None = None
    next_run_at: str | None = None


class RoutinesOrchestrator:
    """Generate due routine tasks and persist execution state."""

    def __init__(self, *, config_path: Path | None = None, state_path: Path) -> None:
        self.config_path = config_path or DEFAULT_ROUTINES_PATH
        self.state_path = state_path
        self.specs = self._load_specs()
        self.state = self._load_state()

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _load_specs(self) -> list[RoutineSpec]:
        if not self.config_path.exists():
            return []
        try:
            import yaml  # type: ignore
        except ImportError:
            payload = self._load_simple_routines_yaml(self.config_path)
        else:
            try:
                payload = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
            except Exception:
                return []
        if not isinstance(payload, dict):
            return []

        routines = payload.get("routines", [])
        specs: list[RoutineSpec] = []
        if not isinstance(routines, list):
            return specs
        for raw in routines:
            if not isinstance(raw, dict):
                continue
            routine_id = raw.get("id")
            prompt = raw.get("prompt")
            if not isinstance(routine_id, str) or not routine_id.strip():
                continue
            if not isinstance(prompt, str) or not prompt.strip():
                continue
            specs.append(
                RoutineSpec(
                    id=routine_id.strip(),
                    prompt=prompt.strip(),
                    description=str(raw.get("description", "")).strip(),
                    interval_minutes=max(1, int(raw.get("interval_minutes", 60))),
                    priority=max(0, int(raw.get("priority", 50))),
                    max_risk=max(0.0, min(1.0, float(raw.get("max_risk", 1.0)))),
                )
            )
        return specs


    def _load_simple_routines_yaml(self, path: Path) -> dict[str, Any]:
        routines: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line == "routines:":
                continue
            if line.startswith("- "):
                if current:
                    routines.append(current)
                current = {}
                line = line[2:].strip()
                if ":" in line:
                    key, value = line.split(":", 1)
                    current[key.strip()] = self._parse_scalar(value)
                continue
            if current is not None and ":" in line:
                key, value = line.split(":", 1)
                current[key.strip()] = self._parse_scalar(value)
        if current:
            routines.append(current)
        return {"routines": routines}

    def _parse_scalar(self, value: str) -> Any:
        text = value.strip().strip('"').strip("'")
        if not text:
            return ""
        try:
            return int(text)
        except ValueError:
            try:
                return float(text)
            except ValueError:
                return text

    def _load_state(self) -> dict[str, RoutineRunState]:
        if not self.state_path.exists():
            return {}
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        routines = payload.get("routines", {}) if isinstance(payload, dict) else {}
        if not isinstance(routines, dict):
            return {}

        state: dict[str, RoutineRunState] = {}
        for key, raw in routines.items():
            if not isinstance(key, str) or not isinstance(raw, dict):
                continue
            state[key] = RoutineRunState(
                last_run_at=raw.get("last_run_at") if isinstance(raw.get("last_run_at"), str) else None,
                last_success=raw.get("last_success") if isinstance(raw.get("last_success"), bool) else None,
                last_latency_ms=float(raw.get("last_latency_ms")) if isinstance(raw.get("last_latency_ms"), (int, float)) else None,
                next_run_at=raw.get("next_run_at") if isinstance(raw.get("next_run_at"), str) else None,
            )
        return state

    def _save_state(self) -> None:
        payload = {
            "routines": {name: asdict(item) for name, item in self.state.items()},
            "updated_at": self._now().isoformat(),
        }
        _atomic_write_text(self.state_path, json.dumps(payload, ensure_ascii=False, indent=2))

    def _parse_iso(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def due_tasks(self) -> list[RoutineTask]:
        now = self._now()
        due: list[RoutineTask] = []
        for spec in self.specs:
            snapshot = self.state.get(spec.id, RoutineRunState())
            next_run = self._parse_iso(snapshot.next_run_at)
            if next_run is None:
                next_run = now
            if next_run > now:
                continue
            deadline = next_run + timedelta(minutes=spec.interval_minutes)
            due.append(
                RoutineTask(
                    id=spec.id,
                    prompt=spec.prompt,
                    description=spec.description,
                    priority=spec.priority,
                    due_at=next_run.isoformat(),
                    deadline_at=deadline.isoformat(),
                    max_risk=spec.max_risk,
                )
            )
        due.sort(key=lambda item: (-item.priority, item.deadline_at))
        return due

    def due_tasks_with_priority_overrides(
        self, priority_overrides: Mapping[str, int] | None
    ) -> list[RoutineTask]:
        tasks = self.due_tasks()
        if not priority_overrides:
            return tasks
        adjusted: list[RoutineTask] = []
        for task in tasks:
            override = priority_overrides.get(task.id)
            if isinstance(override, int):
                adjusted.append(
                    RoutineTask(
                        id=task.id,
                        prompt=task.prompt,
                        description=task.description,
                        priority=max(0, override),
                        due_at=task.due_at,
                        deadline_at=task.deadline_at,
                        max_risk=task.max_risk,
                    )
                )
            else:
                adjusted.append(task)
        adjusted.sort(key=lambda item: (-item.priority, item.deadline_at))
        return adjusted

    def mark_executed(self, task: RoutineTask, *, success: bool, latency_ms: float) -> None:
        executed_at = self._now()
        next_run = executed_at + timedelta(
            minutes=next((spec.interval_minutes for spec in self.specs if spec.id == task.id), 60)
        )
        self.state[task.id] = RoutineRunState(
            last_run_at=executed_at.isoformat(),
            last_success=success,
            last_latency_ms=max(0.0, float(latency_ms)),
            next_run_at=next_run.isoformat(),
        )
        self._save_state()

    def execute_with_runtime(
        self,
        *,
        skill_runtime: Any,
        base_context: dict[str, Any],
        priority_overrides: Mapping[str, int] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute all due routines through the skill runtime."""

        outcomes: list[dict[str, Any]] = []
        for task in self.due_tasks_with_priority_overrides(priority_overrides):
            started = perf_counter()
            result = skill_runtime.execute_best_skill(
                task={
                    "name": f"routine.{task.id}",
                    "capabilities": [],
                    "max_risk": task.max_risk,
                    "priority": task.priority,
                    "due_at": task.due_at,
                    "deadline_at": task.deadline_at,
                    "prompt": task.prompt,
                },
                context={
                    **base_context,
                    "routine": {
                        "id": task.id,
                        "description": task.description,
                        "prompt": task.prompt,
                        "priority": task.priority,
                        "due_at": task.due_at,
                        "deadline_at": task.deadline_at,
                    },
                },
            )
            latency_ms = (perf_counter() - started) * 1000.0
            success = result.status == "succeeded"
            self.mark_executed(task, success=success, latency_ms=latency_ms)
            outcomes.append(
                {
                    "routine": task.id,
                    "status": result.status,
                    "skill": result.skill,
                    "score": result.score,
                    "reason": result.reason,
                    "latency_ms": latency_ms,
                    "priority": task.priority,
                    "deadline_at": task.deadline_at,
                }
            )
        return outcomes
