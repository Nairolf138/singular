"""Central runtime to pick and execute the best skill."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from singular.events import EventBus, get_global_event_bus
from singular.life import sandbox
from singular.memory import read_skills


@dataclass(frozen=True)
class SkillExecutionResult:
    """Result envelope for one runtime skill execution."""

    skill: str | None
    status: str
    score: float | None = None
    output: Any = None
    reason: str | None = None


@dataclass(frozen=True)
class _ScoredCandidate:
    skill: str
    path: Path
    metadata: dict[str, Any]
    score: float


class SkillRuntime:
    """Resolve compatible skills, rank them and run the best candidate."""

    def __init__(
        self,
        *,
        skills_dir: Path,
        mem_dir: Path,
        bus: EventBus | None = None,
    ) -> None:
        self.skills_dir = Path(skills_dir)
        self.mem_dir = Path(mem_dir)
        self.bus = bus or get_global_event_bus()

    def execute_best_skill(self, task: str | dict[str, Any], context: dict[str, Any]) -> SkillExecutionResult:
        """Execute the best compatible skill for ``task`` and ``context``."""

        task_dict = self._normalize_task(task)
        skills_state = read_skills(self.mem_dir / "skills.json")
        candidates = self._compatible_candidates(task_dict, skills_state)
        if not candidates:
            result = SkillExecutionResult(skill=None, status="failed", reason="no_compatible_skill")
            self.bus.publish(
                "skill.execution.failed",
                {
                    "task": task_dict,
                    "reason": result.reason,
                },
            )
            return result

        top = max(candidates, key=lambda item: item.score)
        self.bus.publish(
            "skill.execution.started",
            {
                "task": task_dict,
                "skill": top.skill,
                "score": top.score,
            },
        )
        try:
            code = top.path.read_text(encoding="utf-8")
            wrapped = self._wrap_for_sandbox(code, context)
            output = sandbox.run(wrapped)
            result = SkillExecutionResult(
                skill=top.skill,
                status="succeeded",
                score=top.score,
                output=output,
            )
            self.bus.publish(
                "skill.execution.succeeded",
                {
                    "task": task_dict,
                    "skill": top.skill,
                    "score": top.score,
                    "output": output,
                },
            )
            return result
        except Exception as exc:
            result = SkillExecutionResult(
                skill=top.skill,
                status="failed",
                score=top.score,
                reason=str(exc),
            )
            self.bus.publish(
                "skill.execution.failed",
                {
                    "task": task_dict,
                    "skill": top.skill,
                    "score": top.score,
                    "reason": str(exc),
                },
            )
            return result

    def _compatible_candidates(
        self,
        task: dict[str, Any],
        skills_state: dict[str, Any],
    ) -> list[_ScoredCandidate]:
        required_signature = task.get("signature")
        required_capabilities = set(task.get("capabilities", []))
        max_risk = float(task.get("max_risk", 1.0))

        candidates: list[_ScoredCandidate] = []
        for path in sorted(self.skills_dir.glob("*.py")):
            key = path.stem
            raw_metadata = skills_state.get(key)
            metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
            lifecycle = metadata.get("lifecycle") if isinstance(metadata.get("lifecycle"), dict) else {}
            if lifecycle.get("state") in {"archived", "deleted", "temporarily_disabled"}:
                continue
            signature = metadata.get("signature")
            if isinstance(required_signature, str) and isinstance(signature, str) and signature != required_signature:
                continue
            capabilities = metadata.get("capabilities") if isinstance(metadata.get("capabilities"), list) else []
            if required_capabilities and not required_capabilities.issubset(set(capabilities)):
                continue
            risk = self._estimated_risk(metadata)
            if risk > max_risk:
                continue
            candidates.append(
                _ScoredCandidate(
                    skill=key,
                    path=path,
                    metadata=metadata,
                    score=self._score_candidate(metadata),
                )
            )
        return candidates

    def _score_candidate(self, metadata: dict[str, Any]) -> float:
        metrics = metadata.get("metrics") if isinstance(metadata.get("metrics"), dict) else {}
        usage_count = max(int(metrics.get("usage_count", 0) or 0), 0)
        average_gain = float(metrics.get("average_gain", 0.0) or 0.0)
        average_cost = float(metrics.get("average_cost", 0.0) or 0.0)
        failure_count = max(int(metrics.get("failure_count", 0) or 0), 0)

        success_rate = 0.5
        if usage_count > 0:
            success_rate = max(0.0, min(1.0, 1.0 - (failure_count / usage_count)))

        expected_utility = average_gain
        resource_cost = max(0.0, average_cost)
        risk = self._estimated_risk(metadata)

        return (expected_utility * 0.45) + (success_rate * 0.35) - (resource_cost * 0.1) - (risk * 0.1)

    def _estimated_risk(self, metadata: dict[str, Any]) -> float:
        metrics = metadata.get("metrics") if isinstance(metadata.get("metrics"), dict) else {}
        usage_count = max(int(metrics.get("usage_count", 0) or 0), 0)
        failure_count = max(int(metrics.get("failure_count", 0) or 0), 0)
        historical_risk = (failure_count / usage_count) if usage_count else 0.5
        declared_risk = float(metadata.get("risk", historical_risk) or historical_risk)
        return max(0.0, min(1.0, declared_risk))

    def _normalize_task(self, task: str | dict[str, Any]) -> dict[str, Any]:
        if isinstance(task, str):
            return {"name": task, "capabilities": [], "max_risk": 1.0}
        capabilities = task.get("capabilities") if isinstance(task.get("capabilities"), list) else []
        normalized = {
            "name": str(task.get("name") or "task"),
            "signature": task.get("signature") if isinstance(task.get("signature"), str) else None,
            "capabilities": [str(cap) for cap in capabilities],
            "max_risk": float(task.get("max_risk", 1.0) or 1.0),
        }
        return normalized

    def _wrap_for_sandbox(self, source: str, context: dict[str, Any]) -> str:
        context_literal = repr(context)
        return (
            f"{source}\n\n"
            f"__runtime_context = {context_literal}\n"
            "if 'run' in globals():\n"
            "    result = run(__runtime_context)\n"
            "elif 'result' not in globals():\n"
            "    result = None\n"
        )


def execute_best_skill(task: str | dict[str, Any], context: dict[str, Any]) -> SkillExecutionResult:
    """Convenience API using default paths and global event bus."""

    from singular.memory import get_base_dir, get_mem_dir

    runtime = SkillRuntime(
        skills_dir=get_base_dir() / "skills",
        mem_dir=get_mem_dir(),
    )
    return runtime.execute_best_skill(task, context)
