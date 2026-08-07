"""Deterministic, hardware-free embodiment simulators."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from .contracts import (
    Acknowledgement,
    Command,
    EmbodimentError,
    EmergencyStop,
    ErrorCode,
    Observation,
)


@dataclass
class DeterministicClock:
    current: datetime = field(
        default_factory=lambda: datetime(2024, 1, 1, tzinfo=timezone.utc)
    )

    def now(self) -> str:
        return self.current.isoformat()

    def advance(self, seconds: float) -> str:
        self.current += timedelta(seconds=max(0.0, seconds))
        return self.now()


@dataclass
class ScriptedSensor:
    source: str
    event_type: str
    readings: Iterable[Any] = ()
    clock: DeterministicClock = field(default_factory=DeterministicClock)
    latency_s: float = 0.0
    unavailable_at: frozenset[int] = frozenset()
    _readings: list[Any] = field(init=False, repr=False)
    _index: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        self._readings = list(self.readings)

    def collect(self) -> list[Observation]:
        index = self._index
        self._index += 1
        observed_at = self.clock.advance(self.latency_s)
        if index in self.unavailable_at:
            return [
                Observation(
                    self.event_type,
                    {"status": "unavailable"},
                    self.source,
                    observed_at=observed_at,
                    error=EmbodimentError(
                        ErrorCode.UNAVAILABLE, f"{self.source} unavailable"
                    ),
                )
            ]
        if index >= len(self._readings):
            return []
        value = self._readings[index]
        payload = value if isinstance(value, dict) else {"value": value}
        return [
            Observation(
                self.event_type, dict(payload), self.source, observed_at=observed_at
            )
        ]

    def close(self) -> None:
        return None


class CameraSimulator(ScriptedSensor):
    def __init__(self, frames: Iterable[Any] = (), **kwargs: Any) -> None:
        super().__init__(
            source="sim.camera", event_type="vision", readings=frames, **kwargs
        )


class MicrophoneSimulator(ScriptedSensor):
    def __init__(self, blocks: Iterable[Any] = (), **kwargs: Any) -> None:
        super().__init__(
            source="sim.microphone", event_type="audio", readings=blocks, **kwargs
        )


@dataclass
class ActuatorSimulator:
    clock: DeterministicClock = field(default_factory=DeterministicClock)
    latency_s: float = 0.0
    refused_actions: frozenset[str] = frozenset()
    stop: EmergencyStop = field(default_factory=EmergencyStop)
    commands: list[Command] = field(default_factory=list)

    def execute(self, command: Command) -> Acknowledgement:
        completed_at = self.clock.advance(self.latency_s)
        if self.stop.engaged:
            return Acknowledgement(
                command.action_type,
                False,
                "emergency stop engaged",
                ErrorCode.EMERGENCY_STOP.value,
                completed_at=completed_at,
                command_id=command.command_id,
                actual={"executed": False},
            )
        if command.action_type in self.refused_actions:
            return Acknowledgement(
                command.action_type,
                False,
                "command refused",
                ErrorCode.REFUSED.value,
                completed_at=completed_at,
                command_id=command.command_id,
                actual={"executed": False},
            )
        self.commands.append(command)
        return Acknowledgement(
            command.action_type,
            True,
            "executed",
            completed_at=completed_at,
            command_id=command.command_id,
            actual={"executed": True, "parameters": dict(command.parameters)},
        )

    def emergency_stop(self, reason: str = "operator_request") -> None:
        self.stop.engage(reason)

    def close(self) -> None:
        return None
