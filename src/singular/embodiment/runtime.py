"""Composition runtime joining sensors, perception, and routed effectors.

The class in this module deliberately implements both the ``PerceptionPort`` and
``ActionPort`` structural protocols.  It can therefore be passed directly to an
``AgentRuntime`` without either layer depending on the other.
"""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Iterable, Mapping

from .contracts import (
    Acknowledgement,
    Command,
    EmbodimentError,
    EmergencyStop,
    ErrorCode,
    Observation,
    Sensor,
    utc_now,
)

AuditSink = Callable[[dict[str, Any]], None]


@dataclass
class AdapterStatus:
    kind: str
    healthy: bool = True
    closed: bool = False
    error: str | None = None
    operations: int = 0


@dataclass
class RuntimeState:
    adapters: dict[str, AdapterStatus] = field(default_factory=dict)
    latest_observations: dict[str, Observation] = field(default_factory=dict)
    pending_commands: dict[str, Command] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    emergency_stop: EmergencyStop = field(default_factory=EmergencyStop)
    closed: bool = False


class EmbodimentRuntime:
    """Own multiple adapters and provide deterministic perception/action I/O.

    Every acknowledgement, including a refusal, is converted to an
    ``action.result`` observation.  It is returned by the *next* ``collect`` so
    the mind can perceive measured outcomes rather than treating actuation as a
    terminal side effect.
    """

    def __init__(
        self,
        sensors: Mapping[str, Sensor] | Iterable[Sensor],
        actuators: Mapping[str, Any],
        *,
        emergency_stop: EmergencyStop | None = None,
        audit_sink: AuditSink | None = None,
        dry_run: bool = False,
    ) -> None:
        if isinstance(sensors, Mapping):
            self.sensors = dict(sensors)
        else:
            self.sensors = {
                f"sensor.{index}": sensor for index, sensor in enumerate(sensors)
            }
        self.actuators = dict(actuators)
        self.state = RuntimeState(emergency_stop=emergency_stop or EmergencyStop())
        self.audit_sink = audit_sink
        self.dry_run = dry_run
        self._feedback: deque[Observation] = deque()
        self._lock = RLock()
        for name in self.sensors:
            self.state.adapters[f"sensor:{name}"] = AdapterStatus("sensor")
        for route in self.actuators:
            self.state.adapters[f"actuator:{route}"] = AdapterStatus("actuator")
        self._audit("embodiment.started", {"dry_run": dry_run})

    def _snapshot(self) -> dict[str, Any]:
        stop = self.state.emergency_stop
        return {
            "adapters": {
                name: asdict(status) for name, status in self.state.adapters.items()
            },
            "latest_observations": {
                source: asdict(value)
                for source, value in self.state.latest_observations.items()
            },
            "pending_commands": {
                command_id: asdict(value)
                for command_id, value in self.state.pending_commands.items()
            },
            "errors": list(self.state.errors),
            "emergency_stop": asdict(stop),
            "closed": self.state.closed,
        }

    def _audit(self, event: str, data: Mapping[str, Any] | None = None) -> None:
        if self.audit_sink is not None:
            self.audit_sink(
                {
                    "event": event,
                    "recorded_at": utc_now(),
                    "data": dict(data or {}),
                    "state": self._snapshot(),
                }
            )

    def _record_error(self, adapter: str, exc: BaseException) -> None:
        status = self.state.adapters[adapter]
        status.healthy = False
        status.error = str(exc)
        error = {"adapter": adapter, "message": str(exc), "at": utc_now()}
        self.state.errors.append(error)
        self._audit("embodiment.adapter.failed", error)

    def collect(self) -> list[Observation]:
        """Collect all sensors and prepend queued action-result feedback."""
        with self._lock:
            if self.state.closed:
                return []
            observations = list(self._feedback)
            self._feedback.clear()
            for name, sensor in self.sensors.items():
                key = f"sensor:{name}"
                try:
                    values = sensor.collect()
                    self.state.adapters[key].operations += 1
                except Exception as exc:  # adapters are isolation boundaries
                    self._record_error(key, exc)
                    values = [
                        Observation(
                            "adapter.error",
                            {"adapter": key, "message": str(exc)},
                            key,
                            error=EmbodimentError(ErrorCode.IO_ERROR, str(exc)),
                        )
                    ]
                observations.extend(values)
            for observation in observations:
                self.state.latest_observations[observation.source] = observation
            self._audit("embodiment.perception.collected", {"count": len(observations)})
            return observations

    def execute(self, command: Command) -> Acknowledgement:
        """Route a command and queue its acknowledgement as perception feedback."""
        with self._lock:
            self.state.pending_commands[command.command_id] = command
            self._audit(
                "embodiment.command.pending", {"command_id": command.command_id}
            )
            actuator = self.actuators.get(command.action_type)
            key = f"actuator:{command.action_type}"
            if self.state.emergency_stop.engaged:
                ack = Acknowledgement(
                    command.action_type,
                    False,
                    "emergency stop engaged",
                    ErrorCode.EMERGENCY_STOP.value,
                    command_id=command.command_id,
                    actual={"executed": False},
                )
            elif actuator is None:
                ack = Acknowledgement(
                    command.action_type,
                    False,
                    "no effector configured",
                    ErrorCode.REFUSED.value,
                    command_id=command.command_id,
                    actual={"executed": False},
                )
            elif self.dry_run:
                ack = Acknowledgement(
                    command.action_type,
                    True,
                    "simulated (dry-run)",
                    command_id=command.command_id,
                    actual={"executed": False, "dry_run": True},
                )
            else:
                try:
                    ack = actuator.execute(command)
                    self.state.adapters[key].operations += 1
                except Exception as exc:
                    self._record_error(key, exc)
                    ack = Acknowledgement(
                        command.action_type,
                        False,
                        "actuator failed",
                        str(exc),
                        command_id=command.command_id,
                        actual={"executed": False},
                    )
            self.state.pending_commands.pop(command.command_id, None)
            feedback = Observation(
                "action.result",
                {
                    "action_type": ack.action_type,
                    "success": ack.success,
                    "message": ack.message,
                    "error": ack.error,
                    "actual": dict(ack.actual),
                    "command_id": ack.command_id or command.command_id,
                },
                f"actuator:{command.action_type}",
                observed_at=ack.completed_at,
            )
            self._feedback.append(feedback)
            self.state.latest_observations[feedback.source] = feedback
            self._audit("embodiment.command.acknowledged", feedback.payload)
            return ack

    def request_emergency_stop(self, reason: str = "operator_request") -> None:
        with self._lock:
            self.state.emergency_stop.engage(reason)
            for route, actuator in self.actuators.items():
                try:
                    actuator.emergency_stop(reason)
                except Exception as exc:
                    self._record_error(f"actuator:{route}", exc)
            self._audit("embodiment.emergency_stop", {"reason": reason})

    emergency_stop = request_emergency_stop

    def close(self) -> None:
        """Close every owned resource once, in reverse declaration order."""
        with self._lock:
            if self.state.closed:
                return
            resources = [
                *((f"sensor:{name}", sensor) for name, sensor in self.sensors.items()),
                *(
                    (f"actuator:{name}", actuator)
                    for name, actuator in self.actuators.items()
                ),
            ]
            seen: set[int] = set()
            for key, resource in reversed(resources):
                if id(resource) in seen:
                    self.state.adapters[key].closed = True
                    continue
                seen.add(id(resource))
                close = getattr(resource, "close", None)
                try:
                    if callable(close):
                        close()
                    self.state.adapters[key].closed = True
                except Exception as exc:
                    self._record_error(key, exc)
            self.state.closed = True
            self._audit("embodiment.closed")

    def __enter__(self) -> "EmbodimentRuntime":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def jsonl_audit_sink(path: str | Path) -> AuditSink:
    """Return an audit sink appending one JSON object per line."""
    import json

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    def write(event: dict[str, Any]) -> None:
        with target.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")

    return write


def build_simulated_runtime(
    config: Mapping[str, Any],
    *,
    dry_run: bool = False,
    audit_sink: AuditSink | None = None,
) -> EmbodimentRuntime:
    """Build deterministic adapters from the portable CLI configuration schema."""
    from .simulators import ActuatorSimulator, ScriptedSensor

    sensors: dict[str, ScriptedSensor] = {}
    for index, item in enumerate(config.get("sensors", [])):
        name = str(item.get("name", f"sensor.{index}"))
        sensors[name] = ScriptedSensor(
            source=str(item.get("source", name)),
            event_type=str(item["event_type"]),
            readings=item.get("readings", ()),
            latency_s=float(item.get("latency_s", 0)),
            unavailable_at=frozenset(item.get("unavailable_at", ())),
        )
    actuators = {
        str(item["command"]): ActuatorSimulator(
            latency_s=float(item.get("latency_s", 0)),
            refused_actions=frozenset(item.get("refused_actions", ())),
        )
        for item in config.get("effectors", [])
    }
    return EmbodimentRuntime(sensors, actuators, dry_run=dry_run, audit_sink=audit_sink)


def run_configured_loop(
    runtime: EmbodimentRuntime, config: Mapping[str, Any], *, steps: int
) -> int:
    """Run simple declarative perception/action rules, returning action count."""
    rules = list(config.get("rules", ()))
    count = 0
    for _ in range(max(0, steps)):
        for observation in runtime.collect():
            for rule in rules:
                if rule.get("event_type") != observation.event_type:
                    continue
                parameters = dict(rule.get("parameters", {}))
                if rule.get("include_payload", True):
                    parameters.update(observation.payload)
                runtime.execute(
                    Command(
                        str(rule["command"]),
                        parameters,
                        str(rule.get("intent_goal", "configured_rule")),
                    )
                )
                count += 1
    return count
