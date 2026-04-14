"""Runtime quest orchestration helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

from singular.life.quest import Spec, load as load_spec
from singular.memory import _atomic_write_text, add_episode, get_mem_dir
from singular.psyche import Mood, Psyche
from singular.resource_manager import ResourceManager


@dataclass
class QuestRecord:
    name: str
    status: str
    started_at: str
    origin: str = "external"
    completed_at: str | None = None
    reason: str | None = None


@dataclass
class QuestRuntimeState:
    active: list[QuestRecord] = field(default_factory=list)
    completed: list[QuestRecord] = field(default_factory=list)
    cooldowns: dict[str, str] = field(default_factory=dict)


class QuestRuntime:
    """Load quest specs, trigger them from perception signals and apply outcomes."""

    def __init__(self, *, base_dir: Path, mem_dir: Path | None = None) -> None:
        self.base_dir = base_dir
        self.mem_dir = mem_dir or get_mem_dir()
        self.quests_dir = self.base_dir / "quests"
        self.state_path = self.mem_dir / "quests_state.json"
        self.state = self._load_state()

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _load_state(self) -> QuestRuntimeState:
        if not self.state_path.exists():
            return QuestRuntimeState()
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return QuestRuntimeState()
        if not isinstance(raw, dict):
            return QuestRuntimeState()

        def _records(items: Any) -> list[QuestRecord]:
            out: list[QuestRecord] = []
            if not isinstance(items, list):
                return out
            for item in items:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                status = item.get("status")
                started_at = item.get("started_at")
                if not all(isinstance(v, str) and v for v in (name, status, started_at)):
                    continue
                raw_origin = item.get("origin")
                origin = raw_origin if raw_origin in {"intrinsic", "external"} else "external"
                out.append(
                    QuestRecord(
                        name=name,
                        status=status,
                        started_at=started_at,
                        origin=origin,
                        completed_at=item.get("completed_at") if isinstance(item.get("completed_at"), str) else None,
                        reason=item.get("reason") if isinstance(item.get("reason"), str) else None,
                    )
                )
            return out

        cooldowns: dict[str, str] = {}
        raw_cooldowns = raw.get("cooldowns", {})
        if isinstance(raw_cooldowns, dict):
            for key, value in raw_cooldowns.items():
                if isinstance(key, str) and isinstance(value, str):
                    cooldowns[key] = value
        return QuestRuntimeState(
            active=_records(raw.get("active", [])),
            completed=_records(raw.get("completed", [])),
            cooldowns=cooldowns,
        )

    def _save_state(self) -> None:
        payload = {
            "active": [asdict(item) for item in self.state.active],
            "completed": [asdict(item) for item in self.state.completed[-200:]],
            "cooldowns": self.state.cooldowns,
            "updated_at": self._now().isoformat(),
        }
        _atomic_write_text(self.state_path, json.dumps(payload, ensure_ascii=False, indent=2))

    def _load_specs(self) -> list[Spec]:
        if not self.quests_dir.exists():
            return []
        specs: list[Spec] = []
        for path in sorted(self.quests_dir.glob("*.json")):
            try:
                specs.append(load_spec(path))
            except Exception:
                continue
        return specs

    def _parse_iso(self, value: str) -> datetime | None:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def _is_on_cooldown(self, spec: Spec) -> bool:
        expires = self.state.cooldowns.get(spec.name)
        if not expires:
            return False
        parsed = self._parse_iso(expires)
        return bool(parsed and parsed > self._now())

    def _signal_matches(self, trigger: dict[str, Any], signals: dict[str, Any]) -> bool:
        signal_key = trigger.get("signal")
        if not isinstance(signal_key, str) or not signal_key:
            return False
        if signal_key == "artifact.event_type":
            expected = trigger.get("equals")
            if not isinstance(expected, str):
                return False
            events = signals.get("artifact_events")
            if not isinstance(events, list):
                return False
            for event in events:
                if isinstance(event, dict) and event.get("type") == expected:
                    return True
            return False

        value = signals.get(signal_key)
        if "equals" in trigger:
            return value == trigger.get("equals")
        if "gte" in trigger and isinstance(value, (int, float)):
            return float(value) >= float(trigger["gte"])
        if "lte" in trigger and isinstance(value, (int, float)):
            return float(value) <= float(trigger["lte"])
        if "contains" in trigger:
            needle = trigger.get("contains")
            return isinstance(value, str) and isinstance(needle, str) and needle in value
        return False

    def evaluate_triggers(self, signals: dict[str, Any]) -> list[str]:
        activated: list[str] = []
        active_names = {item.name for item in self.state.active}
        for spec in self._load_specs():
            if spec.name in active_names or self._is_on_cooldown(spec):
                continue
            if not spec.triggers:
                continue
            if all(self._signal_matches(trigger, signals) for trigger in spec.triggers):
                self.state.active.append(
                    QuestRecord(
                        name=spec.name,
                        status="active",
                        started_at=self._now().isoformat(),
                        origin=spec.origin,
                    )
                )
                add_episode(
                    {
                        "event": "quest_triggered",
                        "quest": spec.name,
                        "triggers": spec.triggers,
                    }
                )
                activated.append(spec.name)
        if activated:
            self._save_state()
        return activated

    def _resource_criteria_met(self, criteria: dict[str, Any], rm: ResourceManager) -> bool:
        rules = criteria.get("resource_min")
        if not isinstance(rules, dict):
            return True
        for key, minimum in rules.items():
            if not isinstance(key, str) or not isinstance(minimum, (int, float)):
                return False
            value = getattr(rm, key, None)
            if not isinstance(value, (int, float)) or float(value) < float(minimum):
                return False
        return True

    def _to_mood(self, raw: Any) -> Mood:
        if isinstance(raw, str):
            try:
                return Mood(raw)
            except ValueError:
                return Mood.NEUTRAL
        return Mood.NEUTRAL

    def _apply_effects(
        self,
        *,
        spec: Spec,
        effect: dict[str, Any],
        outcome: str,
        psyche: Psyche,
        resource_manager: ResourceManager,
    ) -> None:
        rm_delta = effect.get("resource_delta")
        if isinstance(rm_delta, dict):
            for key, delta in rm_delta.items():
                if not isinstance(key, str) or not isinstance(delta, (int, float)):
                    continue
                current = getattr(resource_manager, key, None)
                if isinstance(current, (int, float)):
                    setattr(resource_manager, key, float(current) + float(delta))
            resource_manager._clamp()
            resource_manager._save()

        mood = self._to_mood(effect.get("mood"))
        psyche.feel(mood)
        energy_delta = effect.get("psyche_energy")
        if isinstance(energy_delta, (int, float)):
            if energy_delta >= 0:
                psyche.gain(float(energy_delta))
            else:
                psyche.consume(abs(float(energy_delta)))
        psyche.save_state()

        add_episode(
            {
                "event": "quest_resolved",
                "quest": spec.name,
                "outcome": outcome,
                "reward": spec.reward,
                "penalty": spec.penalty,
                "cooldown": spec.cooldown,
            }
        )

    def settle_active(self, *, psyche: Psyche, resource_manager: ResourceManager) -> dict[str, list[str]]:
        specs = {spec.name: spec for spec in self._load_specs()}
        next_active: list[QuestRecord] = []
        successes: list[str] = []
        failures: list[str] = []

        for record in self.state.active:
            spec = specs.get(record.name)
            if spec is None:
                continue
            criteria = spec.success
            success = self._resource_criteria_met(criteria, resource_manager)
            timeout = criteria.get("timeout_seconds") if isinstance(criteria, dict) else None
            timed_out = False
            if isinstance(timeout, (int, float)):
                started = self._parse_iso(record.started_at)
                if started is not None and (self._now() - started).total_seconds() > float(timeout):
                    timed_out = True

            if success:
                self._apply_effects(
                    spec=spec,
                    effect=spec.reward,
                    outcome="success",
                    psyche=psyche,
                    resource_manager=resource_manager,
                )
                self.state.completed.append(
                    QuestRecord(
                        name=spec.name,
                        status="success",
                        started_at=record.started_at,
                        origin=record.origin,
                        completed_at=self._now().isoformat(),
                    )
                )
                self.state.cooldowns[spec.name] = (
                    self._now() + timedelta(seconds=spec.cooldown)
                ).isoformat()
                successes.append(spec.name)
                continue

            if timed_out:
                self._apply_effects(
                    spec=spec,
                    effect=spec.penalty,
                    outcome="failure",
                    psyche=psyche,
                    resource_manager=resource_manager,
                )
                self.state.completed.append(
                    QuestRecord(
                        name=spec.name,
                        status="failure",
                        started_at=record.started_at,
                        origin=record.origin,
                        completed_at=self._now().isoformat(),
                        reason="timeout",
                    )
                )
                self.state.cooldowns[spec.name] = (
                    self._now() + timedelta(seconds=spec.cooldown)
                ).isoformat()
                failures.append(spec.name)
                continue

            next_active.append(record)

        self.state.active = next_active
        if successes or failures:
            self._save_state()
        return {"successes": successes, "failures": failures}

    def snapshot(self) -> dict[str, Any]:
        return {
            "active": [asdict(item) for item in self.state.active],
            "completed": [asdict(item) for item in self.state.completed[-20:]],
        }
