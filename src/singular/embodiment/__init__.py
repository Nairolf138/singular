"""Stable public embodiment API with no hardware dependency."""

from .contracts import (
    Acknowledgement,
    Actuator,
    Command,
    EmbodimentError,
    EmergencyStop,
    ErrorCode,
    Observation,
    Sensor,
)
from .simulators import (
    ActuatorSimulator,
    CameraSimulator,
    DeterministicClock,
    MicrophoneSimulator,
    ScriptedSensor,
)
from .adapters import GPIOActuator, OptionalAdapterUnavailable, ROS2Sensor

__all__ = [
    "Acknowledgement",
    "Actuator",
    "ActuatorSimulator",
    "CameraSimulator",
    "Command",
    "DeterministicClock",
    "EmbodimentError",
    "EmergencyStop",
    "ErrorCode",
    "MicrophoneSimulator",
    "Observation",
    "ScriptedSensor",
    "Sensor",
    "GPIOActuator",
    "OptionalAdapterUnavailable",
    "ROS2Sensor",
]
