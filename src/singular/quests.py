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
    history: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class QuestRuntimeState:
    active: list[QuestRecord] = field(default_factory=list)
    paused: list[QuestRecord] = field(default_factory=list)
    completed: list[QuestRecord] = field(default_factory=list)
    cooldowns: dict[str, str] = field(default_factory=dict)


class ObjectiveArbitrator:
    """Compute per-quest arbitration signals and suggested transition."""

    @staticmethod
    def _clamp(value: float, *, floor: float = 0.0, ceil: float = 1.0) -> float:
        return max(floor, min(ceil, value))

    def assess(
        self,
        *,
        spec: Spec,
        record: QuestRecord,
        resources: ResourceManager,
        health_score: float | None,
        load_score: float | None,
    ) -> dict[str, float | str]:
        reward_signal = float(len(spec.reward)) + float(spec.reward.get("psyche_energy", 0.0) or 0.0) / 15.0
        penalty_signal = float(len(spec.penalty)) + abs(float(spec.penalty.get("psyche_energy", 0.0) or 0.0)) / 12.0
        expected_utility = self._clamp((reward_signal + (0.2 if spec.origin == "intrinsic" else 0.1)) / (reward_signal + penalty_signal + 1.0))

        failures = sum(1 for event in record.history if event.get("to") == "failure")
        pauses = sum(1 for event in record.history if event.get("to") == "paused")
        emotional_cost = self._clamp((failures * 0.35) + (pauses * 0.18) + (0.2 if record.reason == "timeout" else 0.0))

        resources_score = self._clamp((resources.energy + resources.food + resources.warmth) / 300.0)
        health_capacity = self._clamp(float(health_score if isinstance(health_score, (int, float)) else 100.0) / 100.0)
        load_capacity = 1.0 - self._clamp(float(load_score if isinstance(load_score, (int, float)) else 0.0))
        capacity = max(0.0, min(resources_score, health_capacity, load_capacity))

        arbitration = (expected_utility * 0.55) + (capacity * 0.45) - (emotional_cost * 0.5)
        transition = "keep"
        if record.status == "active":
            if capacity < 0.18 or arbitration < 0.05:
                transition = "abandoned" if (emotional_cost > 0.78 or (pauses >= 2 and arbitration < 0.0)) else "paused"
        elif record.status == "paused":
            if arbitration > 0.35 and capacity > 0.4:
                transition = "resumed"
            elif emotional_cost > 0.85 and capacity < 0.2:
                transition = "abandoned"
        return {
            "expected_utility": round(expected_utility, 4),
            "emotional_cost": round(emotional_cost, 4),
            "capacity": round(capacity, 4),
            "arbitration": round(arbitration, 4),
            "transition": transition,
        }


class QuestRuntime:
    """Load quest specs, trigger them from perception signals and apply outcomes."""

    def __init__(self, *, base_dir: Path, mem_dir: Path | None = None) -> None:
        self.base_dir = base_dir
        self.mem_dir = mem_dir or get_mem_dir()
        self.quests_dir = self.base_dir / "quests"
        self.state_path = self.mem_dir / "quests_state.json"
        self.arbitrator = ObjectiveArbitrator()
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
                        history=item.get("history") if isinstance(item.get("history"), list) else [],
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
            paused=_records(raw.get("paused", [])),
            completed=_records(raw.get("completed", [])),
            cooldowns=cooldowns,
        )

    def _save_state(self) -> None:
        payload = {
            "active": [asdict(item) for item in self.state.active],
            "paused": [asdict(item) for item in self.state.paused],
            "completed": [asdict(item) for item in self.state.completed[-200:]],
            "cooldowns": self.state.cooldowns,
            "updated_at": self._now().isoformat(),
        }
        _atomic_write_text(self.state_path, json.dumps(payload, ensure_ascii=False, indent=2))

    def _append_transition(
        self,
        *,
        record: QuestRecord,
        from_status: str,
        to_status: str,
        reason: str,
        arbitration: dict[str, float | str] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "at": self._now().isoformat(),
            "from": from_status,
            "to": to_status,
            "reason": reason,
        }
        if arbitration is not None:
            payload["arbitration"] = {
                "expected_utility": arbitration.get("expected_utility"),
                "emotional_cost": arbitration.get("emotional_cost"),
                "capacity": arbitration.get("capacity"),
                "arbitration": arbitration.get("arbitration"),
            }
        record.history.append(payload)
        record.history = record.history[-100:]

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
                        history=[
                            {
                                "at": self._now().isoformat(),
                                "from": "inactive",
                                "to": "active",
                                "reason": "trigger_matched",
                            }
                        ],
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

    def settle_active(
        self,
        *,
        psyche: Psyche,
        resource_manager: ResourceManager,
        health_score: float | None = None,
        load_score: float | None = None,
    ) -> dict[str, list[str]]:
        specs = {spec.name: spec for spec in self._load_specs()}
        next_active: list[QuestRecord] = []
        next_paused: list[QuestRecord] = []
        successes: list[str] = []
        failures: list[str] = []
        paused: list[str] = []
        resumed: list[str] = []
        abandoned: list[str] = []

        for record in self.state.active:
            spec = specs.get(record.name)
            if spec is None:
                continue
            arbitration = self.arbitrator.assess(
                spec=spec,
                record=record,
                resources=resource_manager,
                health_score=health_score,
                load_score=load_score,
            )
            transition = arbitration.get("transition")
            if transition == "paused":
                self._append_transition(
                    record=record,
                    from_status="active",
                    to_status="paused",
                    reason="objective_arbitration_low_capacity_or_utility",
                    arbitration=arbitration,
                )
                record.status = "paused"
                record.reason = "objective_arbitration_low_capacity_or_utility"
                next_paused.append(record)
                paused.append(spec.name)
                continue
            if transition == "abandoned":
                self._append_transition(
                    record=record,
                    from_status="active",
                    to_status="abandoned",
                    reason="objective_arbitration_high_emotional_cost_or_risk",
                    arbitration=arbitration,
                )
                record.status = "abandoned"
                record.reason = "objective_arbitration_high_emotional_cost_or_risk"
                record.completed_at = self._now().isoformat()
                self.state.completed.append(record)
                self.state.cooldowns[spec.name] = (
                    self._now() + timedelta(seconds=spec.cooldown)
                ).isoformat()
                abandoned.append(spec.name)
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
                        history=record.history,
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
                        history=record.history,
                    )
                )
                self.state.cooldowns[spec.name] = (
                    self._now() + timedelta(seconds=spec.cooldown)
                ).isoformat()
                failures.append(spec.name)
                continue

            next_active.append(record)

        for record in self.state.paused:
            spec = specs.get(record.name)
            if spec is None:
                continue
            arbitration = self.arbitrator.assess(
                spec=spec,
                record=record,
                resources=resource_manager,
                health_score=health_score,
                load_score=load_score,
            )
            transition = arbitration.get("transition")
            if transition == "resumed":
                self._append_transition(
                    record=record,
                    from_status="paused",
                    to_status="resumed",
                    reason="objective_arbitration_capacity_restored",
                    arbitration=arbitration,
                )
                self._append_transition(
                    record=record,
                    from_status="resumed",
                    to_status="active",
                    reason="quest_reentered_execution",
                    arbitration=arbitration,
                )
                record.status = "active"
                record.reason = "objective_arbitration_capacity_restored"
                next_active.append(record)
                resumed.append(spec.name)
                continue
            if transition == "abandoned":
                self._append_transition(
                    record=record,
                    from_status="paused",
                    to_status="abandoned",
                    reason="objective_arbitration_persistent_risk",
                    arbitration=arbitration,
                )
                record.status = "abandoned"
                record.reason = "objective_arbitration_persistent_risk"
                record.completed_at = self._now().isoformat()
                self.state.completed.append(record)
                self.state.cooldowns[spec.name] = (
                    self._now() + timedelta(seconds=spec.cooldown)
                ).isoformat()
                abandoned.append(spec.name)
                continue
            next_paused.append(record)

        self.state.active = next_active
        self.state.paused = next_paused
        if successes or failures or paused or resumed or abandoned:
            self._save_state()
        return {
            "successes": successes,
            "failures": failures,
            "paused": paused,
            "resumed": resumed,
            "abandoned": abandoned,
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "active": [asdict(item) for item in self.state.active],
            "paused": [asdict(item) for item in self.state.paused],
            "completed": [asdict(item) for item in self.state.completed[-20:]],
        }
