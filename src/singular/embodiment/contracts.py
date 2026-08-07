"""Dependency-free contracts shared by embodied inputs and outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Protocol, runtime_checkable
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ErrorCode(str, Enum):
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    REFUSED = "refused"
    EMERGENCY_STOP = "emergency_stop"
    IO_ERROR = "io_error"


@dataclass(frozen=True)
class EmbodimentError:
    code: ErrorCode
    message: str
    recoverable: bool = True
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Observation:
    """A timestamped, source-identifiable sensor reading."""

    event_type: str
    payload: dict[str, Any]
    source: str
    schema_version: str = "1.0"
    observed_at: str = field(default_factory=utc_now)
    observation_id: str = field(default_factory=lambda: uuid4().hex)
    error: EmbodimentError | None = None


@dataclass(frozen=True)
class Command:
    """An actuator command. Commands are proposals until acknowledged."""

    action_type: str
    parameters: dict[str, Any] = field(default_factory=dict)
    intent_goal: str = ""
    schema_version: str = "1.0"
    requested_at: str = field(default_factory=utc_now)
    command_id: str = field(default_factory=lambda: uuid4().hex)


@dataclass(frozen=True)
class Acknowledgement:
    """The measured outcome returned by an actuator, including refusals."""

    action_type: str
    success: bool
    message: str = ""
    error: str | None = None
    audit: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1.0"
    completed_at: str = field(default_factory=utc_now)
    command_id: str | None = None
    actual: dict[str, Any] = field(default_factory=dict)


@dataclass
class EmergencyStop:
    """Latched emergency stop shared by a runtime and its actuators."""

    engaged: bool = False
    reason: str | None = None
    engaged_at: str | None = None

    def engage(self, reason: str = "operator_request") -> None:
        self.engaged = True
        self.reason = reason
        self.engaged_at = utc_now()

    def reset(self) -> None:
        self.engaged = False
        self.reason = None
        self.engaged_at = None


@runtime_checkable
class Sensor(Protocol):
    def collect(self) -> list[Observation]: ...

    def close(self) -> None: ...


@runtime_checkable
class Actuator(Protocol):
    def execute(self, command: Command) -> Acknowledgement: ...

    def emergency_stop(self, reason: str = "operator_request") -> None: ...
