"""Structured orchestration daemon for life ticks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
import json
import logging
import signal
import time
from pathlib import Path
from typing import Any

from singular.events import Event, EventBus, get_global_event_bus
from singular.goals import IntrinsicGoals
from singular.governance.policy import MutationGovernancePolicy
from singular.life.loop import run_tick
from singular.memory import _atomic_write_text, get_base_dir, get_mem_dir
from singular.orchestrator.lifecycle_clock import (
    LifecycleClockConfig,
    load_lifecycle_clock_config,
)
from singular.perception import capture_signals
from singular.psyche import Psyche
from singular.resource_manager import ResourceManager
from singular.quests import QuestRuntime
from singular.sensors import load_host_sensor_thresholds
from singular.skills.runtime import SkillRuntime
from singular.routines import RoutinesOrchestrator

log = logging.getLogger(__name__)


class LifecyclePhase(Enum):
    """High-level phase used by the orchestration loop."""

    VEILLE = "veille"
    ACTION = "action"
    INTROSPECTION = "introspection"
    SOMMEIL = "sommeil"


@dataclass
class SchedulerConfig:
    """Durations (in seconds) for each lifecycle phase."""

    veille_seconds: float = 2.0
    action_seconds: float = 1.0
    introspection_seconds: float = 1.0
    sommeil_seconds: float = 3.0

    def duration_for(self, phase: LifecyclePhase) -> float:
        return {
            LifecyclePhase.VEILLE: self.veille_seconds,
            LifecyclePhase.ACTION: self.action_seconds,
            LifecyclePhase.INTROSPECTION: self.introspection_seconds,
            LifecyclePhase.SOMMEIL: self.sommeil_seconds,
        }[phase]


@dataclass
class OrchestratorState:
    """Persisted daemon state to support resume/restart."""

    current_phase: str = LifecyclePhase.VEILLE.value
    next_wakeup_at: str | None = None
    last_events: list[dict[str, Any]] = field(default_factory=list)
    last_run_mtime: float | None = None
    last_watch_mtime: float | None = None


@dataclass
class OrchestratorConfig:
    """Runtime configuration for the orchestrator daemon."""

    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    poll_interval_seconds: float = 0.3
    tick_budget_seconds: float = 0.2
    introspection_frequency_ticks: int = 1
    mutation_window_seconds: float = 0.2
    phase_behaviors: dict[str, dict[str, Any]] = field(default_factory=dict)
    dry_run: bool = False
    safe_mode: bool = False


class OrchestratorService:
    """Drive structured ticks across perception/metabolism/cognition/mutation/sleep."""

    def __init__(
        self,
        *,
        config: OrchestratorConfig,
        bus: EventBus | None = None,
        base_dir: Path | None = None,
    ) -> None:
        self.config = config
        self.bus = bus or get_global_event_bus()
        self.base_dir = base_dir or get_base_dir()
        self.mem_dir = get_mem_dir()
        self.state_path = self.mem_dir / "orchestrator_state.json"
        self.checkpoint_path = self.base_dir / "life_checkpoint.json"
        self.skills_dir = self.base_dir / "skills"
        self.resources_path = self.base_dir / "resources.json"

        self.state = self._load_state()
        self.resource_manager = ResourceManager(path=self.resources_path)
        self.psyche = Psyche.load_state()
        self.quest_runtime = QuestRuntime(base_dir=self.base_dir, mem_dir=self.mem_dir)
        self.skill_runtime = SkillRuntime(
            skills_dir=self.skills_dir,
            mem_dir=self.mem_dir,
            bus=self.bus,
        )
        self.governance_policy = MutationGovernancePolicy(safe_mode=self.config.safe_mode)
        self.routines = RoutinesOrchestrator(state_path=self.mem_dir / "routines_state.json")
        self.goals = IntrinsicGoals(path=self.mem_dir / "goals.json")
        self._running = False
        self._wake_requested = False
        self._pending_events: list[dict[str, Any]] = []
        self._tick_count = 0
        self._latest_signals: dict[str, Any] = {}
        self._host_thresholds = load_host_sensor_thresholds()

        self._subscribe_external_stimuli()

    def _subscribe_external_stimuli(self) -> None:
        for event_type in (
            "watch.significant_change",
            "mutation.applied",
            "mutation.rejected",
            "signal.captured",
        ):
            self.bus.subscribe(event_type, self._on_external_event)

    def _on_external_event(self, event: Event) -> None:
        self._wake_requested = True
        self._pending_events.append(
            {
                "event_type": event.event_type,
                "emitted_at": event.emitted_at,
            }
        )
        self._pending_events = self._pending_events[-50:]

    def _load_state(self) -> OrchestratorState:
        if not self.state_path.exists():
            return OrchestratorState()
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return OrchestratorState()
        if not isinstance(raw, dict):
            return OrchestratorState()
        return OrchestratorState(
            current_phase=str(raw.get("current_phase", LifecyclePhase.VEILLE.value)),
            next_wakeup_at=raw.get("next_wakeup_at"),
            last_events=list(raw.get("last_events", [])),
            last_run_mtime=raw.get("last_run_mtime"),
            last_watch_mtime=raw.get("last_watch_mtime"),
        )

    def _save_state(self) -> None:
        payload = {
            "current_phase": self.state.current_phase,
            "next_wakeup_at": self.state.next_wakeup_at,
            "last_events": self.state.last_events[-100:],
            "last_run_mtime": self.state.last_run_mtime,
            "last_watch_mtime": self.state.last_watch_mtime,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _atomic_write_text(self.state_path, json.dumps(payload, ensure_ascii=False, indent=2))

    def _next_phase(self, phase: LifecyclePhase) -> LifecyclePhase:
        order = [
            LifecyclePhase.VEILLE,
            LifecyclePhase.ACTION,
            LifecyclePhase.INTROSPECTION,
            LifecyclePhase.SOMMEIL,
        ]
        index = order.index(phase)
        return order[(index + 1) % len(order)]

    def _push_event(self, phase: LifecyclePhase, details: dict[str, Any]) -> None:
        self.state.last_events.append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "phase": phase.value,
                "details": details,
            }
        )
        self.state.last_events = self.state.last_events[-100:]

    def _runs_mtime(self) -> float | None:
        runs_dir = self.base_dir / "runs"
        if not runs_dir.exists():
            return None
        mtimes = [entry.stat().st_mtime for entry in runs_dir.rglob("*.jsonl")]
        return max(mtimes, default=None)

    def _watch_mtime(self) -> float | None:
        candidates = [
            self.base_dir / "runs",
            self.base_dir / "skills",
            self.mem_dir / "inbox.json",
        ]
        latest: float | None = None
        for item in candidates:
            if not item.exists():
                continue
            try:
                current = item.stat().st_mtime
            except OSError:
                continue
            if latest is None or current > latest:
                latest = current
        return latest

    def _external_stimulus_detected(self) -> bool:
        latest_run = self._runs_mtime()
        latest_watch = self._watch_mtime()

        run_changed = (
            latest_run is not None
            and (
                self.state.last_run_mtime is None
                or latest_run > self.state.last_run_mtime
            )
        )
        watch_changed = (
            latest_watch is not None
            and (
                self.state.last_watch_mtime is None
                or latest_watch > self.state.last_watch_mtime
            )
        )

        self.state.last_run_mtime = latest_run
        self.state.last_watch_mtime = latest_watch

        return self._wake_requested or run_changed or watch_changed

    def _run_phase(self, phase: LifecyclePhase) -> None:
        if phase is LifecyclePhase.VEILLE:
            signals = capture_signals(bus=self.bus)
            self._latest_signals = dict(signals)
            activated = self.quest_runtime.evaluate_triggers(signals)
            self._push_event(
                phase,
                {"signals": list(signals.keys()), "quests_triggered": activated},
            )
            return

        if phase is LifecyclePhase.ACTION:
            self.resource_manager.metabolize()
            mood = self.psyche.update_from_resource_manager(self.resource_manager)
            behavior = self.config.phase_behaviors.get(phase.value, {})
            fatigue_slowdown = float(behavior.get("slowdown_on_fatigue", 1.0))
            cpu_budget_percent = float(behavior.get("cpu_budget_percent", 100.0))
            tick_budget = min(
                self.config.tick_budget_seconds,
                self.config.mutation_window_seconds,
            )
            if mood.value == "fatigue":
                tick_budget *= max(fatigue_slowdown, 1.0)
            adaptation = self._compute_runtime_adaptation()
            tick_budget *= adaptation["tick_budget_scale"]
            tick_budget = max(0.01, min(tick_budget, self.config.mutation_window_seconds))
            cpu_budget_percent *= adaptation["cpu_budget_scale"]
            previous_safe_mode = bool(self.governance_policy.safe_mode)
            self.governance_policy.safe_mode = bool(adaptation["enforce_prudent_mode"])
            if (
                adaptation["rule_triggers"]
                or previous_safe_mode != self.governance_policy.safe_mode
                or bool(adaptation["allow_aggressive_exploration"])
            ):
                audit_payload = {
                    "phase": phase.value,
                    "tick_count": self._tick_count,
                    "triggered_rules": adaptation["rule_triggers"],
                    "host_metrics": adaptation["host_metrics"],
                    "resource_snapshot": adaptation["resource_snapshot"],
                    "tick_budget_seconds": tick_budget,
                    "cpu_budget_percent": cpu_budget_percent,
                    "safe_mode": self.governance_policy.safe_mode,
                    "aggressive_exploration": adaptation["allow_aggressive_exploration"],
                    "skip_action_tick": adaptation["skip_action_tick"],
                }
                self.bus.publish("orchestrator.adaptation", audit_payload, payload_version=1)
                log.info("orchestrator adaptation applied: %s", audit_payload)
                self._push_event(phase, {"adaptation": audit_payload})
            if adaptation["skip_action_tick"]:
                self.psyche.sleep_tick()
                self.psyche.sleeping = True
                self._push_event(
                    phase,
                    {
                        "skipped": True,
                        "reason": "thermal_guard",
                        "tick_budget_seconds": tick_budget,
                        "safe_mode": self.governance_policy.safe_mode,
                    },
                )
                return
            skill_execution = None
            execution_strategy: dict[str, Any] | None = None
            routine_executions: list[dict[str, Any]] = []
            if not self.config.dry_run:
                strategy = self.goals.derive_execution_strategy(self._latest_signals)
                execution_strategy = dict(strategy)
                if adaptation["allow_aggressive_exploration"]:
                    execution_strategy["exploration_intensity"] = "aggressive"
                    execution_strategy["adaptation_source"] = "stable_resources"
                routine_specs = [
                    {"id": spec.id, "prompt": spec.prompt, "priority": spec.priority}
                    for spec in self.routines.specs
                ]
                adjusted_routines = self.goals.adjust_routine_priorities(
                    routine_specs,
                    perception_signals=self._latest_signals,
                )
                priority_overrides = {
                    item["id"]: int(item["priority"])
                    for item in adjusted_routines
                    if "id" in item
                }
                action_context = {
                    "phase": phase.value,
                    "mood": mood.value,
                    "energy": self.resource_manager.energy,
                    "food": self.resource_manager.food,
                    "execution_strategy": execution_strategy,
                }
                skill_execution = self.skill_runtime.execute_best_skill(
                    task={"name": "orchestrator.action", "capabilities": []},
                    context=action_context,
                )
                routine_executions = self.routines.execute_with_runtime(
                    skill_runtime=self.skill_runtime,
                    base_context=action_context,
                    priority_overrides=priority_overrides,
                )
                run_tick(
                    skills_dirs=self.skills_dir,
                    checkpoint_path=self.checkpoint_path,
                    run_id="orchestrator",
                    event_bus=self.bus,
                    resource_manager=self.resource_manager,
                    tick_budget_seconds=tick_budget,
                    governance_policy=self.governance_policy,
                )
            quest_outcomes = self.quest_runtime.settle_active(
                psyche=self.psyche,
                resource_manager=self.resource_manager,
            )
            self._push_event(
                phase,
                {
                    "energy": self.resource_manager.energy,
                    "food": self.resource_manager.food,
                    "mood": mood.value,
                    "cpu_budget_percent": cpu_budget_percent,
                    "tick_budget_seconds": tick_budget,
                    "safe_mode": self.governance_policy.safe_mode,
                    "allowed_actions": behavior.get("allowed_actions", []),
                    "quests": quest_outcomes,
                    "routines": routine_executions,
                    "skill_execution": (
                        {
                            "skill": skill_execution.skill,
                            "status": skill_execution.status,
                            "score": skill_execution.score,
                            "reason": skill_execution.reason,
                        }
                        if skill_execution is not None
                        else None
                    ),
                    "execution_strategy": execution_strategy,
                },
            )
            return

        if phase is LifecyclePhase.INTROSPECTION:
            if self._tick_count % self.config.introspection_frequency_ticks != 0:
                self._push_event(phase, {"skipped": True, "reason": "frequency_gate"})
                return
            mood = self.psyche.update_from_resource_manager(self.resource_manager)
            self.psyche.save_state()
            self._push_event(phase, {"mood": mood.value, "energy": self.psyche.energy})
            return

        self.psyche.sleep_tick()
        self.psyche.sleeping = True
        self.psyche.save_state()
        self._push_event(phase, {"energy": self.psyche.energy})

    def _compute_runtime_adaptation(self) -> dict[str, Any]:
        host_metrics = self._latest_signals.get("host_metrics", {})
        if not isinstance(host_metrics, dict):
            host_metrics = {}

        cpu_percent = float(host_metrics.get("cpu_percent", 0.0) or 0.0)
        ram_used_percent = float(host_metrics.get("ram_used_percent", 0.0) or 0.0)
        host_temperature_c = host_metrics.get("host_temperature_c")
        if not isinstance(host_temperature_c, (int, float)):
            host_temperature_c = self._latest_signals.get("temperature")
        if not isinstance(host_temperature_c, (int, float)):
            host_temperature_c = 0.0
        host_temperature_c = float(host_temperature_c)

        tick_budget_scale = 1.0
        cpu_budget_scale = 1.0
        enforce_prudent_mode = bool(self.config.safe_mode)
        skip_action_tick = False
        allow_aggressive_exploration = False
        rule_triggers: list[str] = []

        # Explicit rule 1: high CPU => reduce action frequency/tick budget.
        if cpu_percent >= self._host_thresholds.cpu_critical_percent:
            tick_budget_scale *= 0.45
            cpu_budget_scale *= 0.55
            rule_triggers.append("cpu_high_critical")
        elif cpu_percent >= self._host_thresholds.cpu_warning_percent:
            tick_budget_scale *= 0.65
            cpu_budget_scale *= 0.75
            rule_triggers.append("cpu_high_warning")

        # Explicit rule 2: RAM pressure => limit costly mutations.
        if ram_used_percent >= self._host_thresholds.ram_critical_percent:
            tick_budget_scale *= 0.5
            enforce_prudent_mode = True
            rule_triggers.append("ram_pressure_critical")
        elif ram_used_percent >= self._host_thresholds.ram_warning_percent:
            tick_budget_scale *= 0.75
            rule_triggers.append("ram_pressure_warning")

        # Explicit rule 3: high temperature => prudent mode / sleep.
        if host_temperature_c >= self._host_thresholds.temperature_critical_c:
            enforce_prudent_mode = True
            skip_action_tick = True
            rule_triggers.append("thermal_critical_sleep")
        elif host_temperature_c >= self._host_thresholds.temperature_warning_c:
            enforce_prudent_mode = True
            tick_budget_scale *= 0.8
            rule_triggers.append("thermal_warning_prudent")

        # Explicit rule 4: stable resources => allow more aggressive exploration.
        resources_stable = (
            cpu_percent < (self._host_thresholds.cpu_warning_percent * 0.6)
            and ram_used_percent < (self._host_thresholds.ram_warning_percent * 0.7)
            and host_temperature_c < (self._host_thresholds.temperature_warning_c - 10.0)
            and self.resource_manager.energy >= 60.0
            and self.resource_manager.food >= 40.0
        )
        if resources_stable and not enforce_prudent_mode:
            tick_budget_scale *= 1.25
            allow_aggressive_exploration = True
            rule_triggers.append("resources_stable_explore")

        return {
            "tick_budget_scale": tick_budget_scale,
            "cpu_budget_scale": cpu_budget_scale,
            "enforce_prudent_mode": enforce_prudent_mode,
            "skip_action_tick": skip_action_tick,
            "allow_aggressive_exploration": allow_aggressive_exploration,
            "rule_triggers": rule_triggers,
            "host_metrics": {
                "cpu_percent": cpu_percent,
                "ram_used_percent": ram_used_percent,
                "host_temperature_c": host_temperature_c,
            },
            "resource_snapshot": {
                "energy": self.resource_manager.energy,
                "food": self.resource_manager.food,
                "warmth": self.resource_manager.warmth,
            },
        }

    def tick(self) -> LifecyclePhase:
        self._tick_count += 1
        phase = LifecyclePhase(self.state.current_phase)
        self._run_phase(phase)

        self.state.last_events.extend(self._pending_events)
        self.state.last_events = self.state.last_events[-100:]
        self._pending_events = []
        self._wake_requested = False

        next_phase = self._next_phase(phase)
        self.state.current_phase = next_phase.value
        wakeup_at = datetime.now(timezone.utc) + timedelta(
            seconds=max(self.config.scheduler.duration_for(next_phase), 0.1)
        )
        self.state.next_wakeup_at = wakeup_at.isoformat()
        self._save_state()
        return next_phase

    def run_forever(self) -> None:
        self._running = True

        def _handle_signal(_signum: int, _frame: Any) -> None:
            self._running = False

        previous_int = signal.signal(signal.SIGINT, _handle_signal)
        previous_term = signal.signal(signal.SIGTERM, _handle_signal)

        try:
            while self._running:
                self.tick()
                if self._external_stimulus_detected():
                    continue
                time.sleep(max(self.config.poll_interval_seconds, 0.05))
        finally:
            signal.signal(signal.SIGINT, previous_int)
            signal.signal(signal.SIGTERM, previous_term)
            self._save_state()


def run_orchestrator_daemon(
    *,
    veille_seconds: float | None,
    action_seconds: float | None,
    introspection_seconds: float | None,
    sommeil_seconds: float | None,
    poll_interval_seconds: float | None,
    tick_budget_seconds: float | None,
    lifecycle_config_path: str | None,
    dry_run: bool,
    safe_mode: bool,
) -> int:
    """CLI entry point for ``singular orchestrate run``."""

    lifecycle_clock: LifecycleClockConfig = load_lifecycle_clock_config(
        Path(lifecycle_config_path) if lifecycle_config_path else None
    )
    resolved_veille = (
        veille_seconds
        if veille_seconds is not None
        else lifecycle_clock.cycle.veille_seconds
    )
    resolved_sommeil = (
        sommeil_seconds
        if sommeil_seconds is not None
        else lifecycle_clock.cycle.sommeil_seconds
    )
    resolved_introspection = (
        introspection_seconds
        if introspection_seconds is not None
        else 1.0
    )
    resolved_action = action_seconds if action_seconds is not None else 1.0
    resolved_poll = poll_interval_seconds if poll_interval_seconds is not None else 0.3
    resolved_tick_budget = (
        tick_budget_seconds
        if tick_budget_seconds is not None
        else lifecycle_clock.cycle.mutation_window_seconds
    )
    service = OrchestratorService(
        config=OrchestratorConfig(
            scheduler=SchedulerConfig(
                veille_seconds=resolved_veille,
                action_seconds=resolved_action,
                introspection_seconds=float(resolved_introspection),
                sommeil_seconds=resolved_sommeil,
            ),
            poll_interval_seconds=resolved_poll,
            tick_budget_seconds=resolved_tick_budget,
            introspection_frequency_ticks=lifecycle_clock.cycle.introspection_frequency_ticks,
            mutation_window_seconds=lifecycle_clock.cycle.mutation_window_seconds,
            phase_behaviors={
                phase: {
                    "cpu_budget_percent": behavior.cpu_budget_percent,
                    "allowed_actions": list(behavior.allowed_actions),
                    "slowdown_on_fatigue": behavior.slowdown_on_fatigue,
                }
                for phase, behavior in lifecycle_clock.phases.items()
            },
            dry_run=dry_run,
            safe_mode=safe_mode,
        )
    )
    print(
        "Orchestrateur démarré "
        f"(veille={resolved_veille}s, action={resolved_action}s, introspection={resolved_introspection}s, sommeil={resolved_sommeil}s)"
    )
    try:
        service.run_forever()
    except KeyboardInterrupt:
        pass
    print("Orchestrateur arrêté proprement.")
    return 0
