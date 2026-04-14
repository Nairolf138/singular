"""Central runtime to pick and execute the best skill."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from singular.environment import sim_world
from singular.events import EventBus, get_global_event_bus
from singular.life import sandbox
from singular.life.skill_catalog import read_skill_catalog, refresh_skill_catalog
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
        catalog = read_skill_catalog(self.mem_dir)
        if not catalog:
            catalog = refresh_skill_catalog(skills_dir=self.skills_dir, mem_dir=self.mem_dir)

        strategy = context.get("execution_strategy", {}) if isinstance(context, dict) else {}
        candidates = self._compatible_candidates(task_dict, skills_state, catalog, strategy=strategy)
        if not candidates:
            result = SkillExecutionResult(skill=None, status="failed", reason="no_compatible_skill")
            self._apply_world_effect("skill.execution.no_compatible")
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
            self._apply_world_effect("skill.execution.succeeded")
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
            self._apply_world_effect("skill.execution.failed")
            return result

    def _apply_world_effect(self, action_type: str) -> None:
        effect = sim_world.map_action_type_to_effect(action_type)
        if not effect:
            return
        state_path = self.mem_dir / "world_state.json"
        effects_path = self.mem_dir / "world_effects.json"
        sim_world.apply_action_effects(
            [effect],
            state_path=state_path,
            effects_path=effects_path,
        )
        self.bus.publish(
            "world.effect.applied",
            {
                "action_type": action_type,
                "effect": effect,
            },
            payload_version=1,
        )

    def _compatible_candidates(
        self,
        task: dict[str, Any],
        skills_state: dict[str, Any],
        catalog: dict[str, dict[str, Any]],
        *,
        strategy: dict[str, Any] | None = None,
    ) -> list[_ScoredCandidate]:
        required_signature = task.get("signature")
        required_capabilities = set(task.get("capabilities", []))
        required_preconditions = set(task.get("preconditions", []))
        required_input = task.get("input_format")
        required_output = task.get("output_format")
        max_risk = float(task.get("max_risk", 1.0))

        candidates: list[_ScoredCandidate] = []
        for skill, descriptor in sorted(catalog.items()):
            path = self.skills_dir / f"{skill}.py"
            if not path.exists():
                continue
            if descriptor.get("annotation_valid") is False:
                continue

            raw_metadata = skills_state.get(skill)
            metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
            lifecycle = metadata.get("lifecycle") if isinstance(metadata.get("lifecycle"), dict) else {}
            if lifecycle.get("state") in {"archived", "deleted", "temporarily_disabled"}:
                continue

            signature = metadata.get("signature") if isinstance(metadata.get("signature"), str) else None
            if isinstance(required_signature, str) and isinstance(signature, str) and signature != required_signature:
                continue

            descriptor_caps = descriptor.get("capability_tags") if isinstance(descriptor.get("capability_tags"), list) else []
            metadata_caps = metadata.get("capabilities") if isinstance(metadata.get("capabilities"), list) else []
            capability_tags = {str(cap) for cap in [*descriptor_caps, *metadata_caps]}
            if required_capabilities and not required_capabilities.issubset(capability_tags):
                continue

            preconditions = set(descriptor.get("preconditions", []))
            if required_preconditions and not required_preconditions.issubset(preconditions):
                continue

            if isinstance(required_input, str) and descriptor.get("input_format") not in {required_input, "unknown"}:
                continue
            if isinstance(required_output, str) and descriptor.get("output_format") not in {required_output, "unknown"}:
                continue

            risk = self._estimated_risk(metadata, descriptor)
            if risk > max_risk:
                continue
            candidates.append(
                _ScoredCandidate(
                    skill=skill,
                    path=path,
                    metadata={"state": metadata, "catalog": descriptor},
                    score=self._score_candidate(metadata, descriptor, strategy=strategy),
                )
            )
        return candidates

    def _score_candidate(
        self,
        metadata: dict[str, Any],
        descriptor: dict[str, Any],
        *,
        strategy: dict[str, Any] | None = None,
    ) -> float:
        metrics = metadata.get("metrics") if isinstance(metadata.get("metrics"), dict) else {}
        usage_count = max(int(metrics.get("usage_count", 0) or 0), 0)
        average_gain = float(metrics.get("average_gain", 0.0) or 0.0)
        average_cost = float(metrics.get("average_cost", descriptor.get("estimated_cost", 0.5)) or 0.0)
        failure_count = max(int(metrics.get("failure_count", 0) or 0), 0)

        success_rate = float(descriptor.get("reliability", 0.5) or 0.5)
        if usage_count > 0:
            historical_success = max(0.0, min(1.0, 1.0 - (failure_count / usage_count)))
            success_rate = (success_rate * 0.4) + (historical_success * 0.6)

        expected_utility = average_gain
        resource_cost = max(0.0, average_cost)
        risk = self._estimated_risk(metadata, descriptor)
        mode = str((strategy or {}).get("mode", "balanced"))
        frustration = max(0.0, min(1.0, float((strategy or {}).get("frustration", 0.0) or 0.0))
        )
        urgency = max(0.0, min(1.0, float((strategy or {}).get("urgency", 0.0) or 0.0)))

        utility_w = 0.45
        success_w = 0.35
        cost_w = 0.1
        risk_w = 0.1
        if mode == "cautious":
            success_w += 0.12 + frustration * 0.08
            risk_w += 0.16 + frustration * 0.08
            utility_w -= 0.08
            expected_utility *= 0.7 + (0.3 * success_rate)
            risk = min(1.0, risk + (frustration * 0.15))
        elif mode == "utility_focused":
            utility_w += 0.12 + urgency * 0.08
            cost_w += 0.05
            risk_w -= 0.03
        elif mode == "exploratory":
            novelty_bonus = max(0.0, 1.0 - (usage_count / 10.0))
            expected_utility += novelty_bonus * 0.15
            risk_w -= 0.03

        return (expected_utility * utility_w) + (success_rate * success_w) - (resource_cost * cost_w) - (risk * risk_w)

    def _estimated_risk(self, metadata: dict[str, Any], descriptor: dict[str, Any]) -> float:
        metrics = metadata.get("metrics") if isinstance(metadata.get("metrics"), dict) else {}
        usage_count = max(int(metrics.get("usage_count", 0) or 0), 0)
        failure_count = max(int(metrics.get("failure_count", 0) or 0), 0)
        historical_risk = (failure_count / usage_count) if usage_count else 0.5
        declared_risk = float(metadata.get("risk", 1.0 - float(descriptor.get("reliability", 0.5))) or historical_risk)
        return max(0.0, min(1.0, declared_risk))

    def _normalize_task(self, task: str | dict[str, Any]) -> dict[str, Any]:
        if isinstance(task, str):
            return {"name": task, "capabilities": [], "preconditions": [], "max_risk": 1.0}
        capabilities = task.get("capabilities") if isinstance(task.get("capabilities"), list) else []
        preconditions = task.get("preconditions") if isinstance(task.get("preconditions"), list) else []
        normalized = {
            "name": str(task.get("name") or "task"),
            "signature": task.get("signature") if isinstance(task.get("signature"), str) else None,
            "capabilities": [str(cap) for cap in capabilities],
            "preconditions": [str(pre) for pre in preconditions],
            "input_format": task.get("input_format") if isinstance(task.get("input_format"), str) else None,
            "output_format": task.get("output_format") if isinstance(task.get("output_format"), str) else None,
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
