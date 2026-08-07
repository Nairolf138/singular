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
from .adapters import (
    GPIOActuator,
    OptionalAdapterUnavailable,
    ROS2ActionActuator,
    ROS2PublisherActuator,
    ROS2QoS,
    ROS2Sensor,
    ROS2ServiceActuator,
    populate_ros_message,
    serialize_ros_message,
)
from .bridge import BridgePorts, build_bridge_ports, load_bridge_config
from .runtime import (
    AdapterStatus,
    EmbodimentRuntime,
    RuntimeState,
    build_simulated_runtime,
    jsonl_audit_sink,
    run_configured_loop,
)

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
    "ROS2QoS",
    "ROS2PublisherActuator",
    "ROS2ServiceActuator",
    "ROS2ActionActuator",
    "serialize_ros_message",
    "populate_ros_message",
    "BridgePorts",
    "build_bridge_ports",
    "load_bridge_config",
    "AdapterStatus",
    "EmbodimentRuntime",
    "RuntimeState",
    "jsonl_audit_sink",
    "build_simulated_runtime",
    "run_configured_loop",
]
