"""Declarative construction of ROS2 perception and action ports."""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .adapters import (
    ROS2ActionActuator,
    ROS2PublisherActuator,
    ROS2QoS,
    ROS2Sensor,
    ROS2ServiceActuator,
)
from .contracts import Acknowledgement, Command, EmergencyStop, ErrorCode, Observation


def resolve_type(path: str) -> Any:
    """Resolve ``package.msg.Type`` (and ordinary dotted Python names)."""
    module, _, name = path.rpartition(".")
    if not module:
        raise ValueError(f"invalid ROS type {path!r}")
    return getattr(importlib.import_module(module), name)


def _get(data: Mapping[str, Any], path: str) -> Any:
    value: Any = data
    for part in path.split("."):
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def payload_transform(spec: Mapping[str, Any] | None):
    """Create a safe field-selection/renaming transform (no expression eval)."""
    spec = spec or {}
    fields = spec.get("fields", {})
    constants = spec.get("constants", {})

    def transform(value: Any) -> dict[str, Any]:
        source = value.parameters if isinstance(value, Command) else value
        result = {
            target: _get(source, source_path) for target, source_path in fields.items()
        }
        result.update(constants)
        return result if fields or constants else dict(source)

    return transform


class SensorGroup:
    def __init__(self, sensors: list[Any]) -> None:
        self.sensors = sensors

    def collect(self) -> list[Observation]:
        return [event for sensor in self.sensors for event in sensor.collect()]

    def close(self) -> None:
        for sensor in self.sensors:
            sensor.close()


class ActionRouter:
    def __init__(self, actuators: Mapping[str, Any], stop: EmergencyStop) -> None:
        self.actuators, self.stop = dict(actuators), stop

    def execute(self, command: Command) -> Acknowledgement:
        actuator = self.actuators.get(command.action_type)
        if actuator is None:
            return Acknowledgement(
                command.action_type,
                False,
                "no configured ROS2 effector",
                ErrorCode.REFUSED.value,
                command_id=command.command_id,
            )
        return actuator.execute(command)

    def emergency_stop(self, reason: str = "operator_request") -> None:
        self.stop.engage(reason)
        for actuator in self.actuators.values():
            actuator.emergency_stop(reason)

    def close(self) -> None:
        for actuator in self.actuators.values():
            actuator.close()


@dataclass(frozen=True)
class BridgePorts:
    """Ports passed as ``perception=`` and ``action=`` to AgentRuntime."""

    perception: SensorGroup
    action: ActionRouter


def load_bridge_config(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return json.loads(text)
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("YAML bridge files require the 'yaml' extra") from exc
    result = yaml.safe_load(text)
    if not isinstance(result, dict):
        raise ValueError("bridge configuration must be a mapping")
    return result


def build_bridge_ports(
    config: Mapping[str, Any] | str | Path, *, node: Any | None = None
) -> BridgePorts:
    """Build AgentRuntime-compatible ports from a validated declarative mapping."""
    if isinstance(config, (str, Path)):
        config = load_bridge_config(config)
    stop = EmergencyStop()
    defaults = config.get("defaults", {})
    default_qos = defaults.get("qos", {})
    sensors = []
    for item in config.get("sensors", []):
        qos = ROS2QoS(**(default_qos | item.get("qos", {})))
        sensors.append(
            ROS2Sensor(
                item["topic"],
                resolve_type(item["message_type"]),
                qos=qos,
                timeout_s=float(item.get("timeout_s", defaults.get("timeout_s", 0))),
                reconnect=bool(item.get("reconnect", True)),
                transform=payload_transform(item.get("transform")),
                node=node,
            )
        )
    actuators = {}
    for item in config.get("effectors", []):
        common = {
            "timeout_s": float(item.get("timeout_s", defaults.get("timeout_s", 2))),
            "transform": payload_transform(item.get("transform")),
            "node": node,
            "stop": stop,
        }
        kind = item["kind"]
        ros_type = resolve_type(item["message_type"])
        if kind == "publisher":
            ack_type = (
                resolve_type(item["acknowledgement_type"])
                if item.get("acknowledgement_type")
                else None
            )
            actuator = ROS2PublisherActuator(
                item["topic"],
                ros_type,
                qos=ROS2QoS(**(default_qos | item.get("qos", {}))),
                acknowledgement_topic=item.get("acknowledgement_topic"),
                acknowledgement_type=ack_type,
                **common,
            )
        elif kind == "service":
            actuator = ROS2ServiceActuator(item["service"], ros_type, **common)
        elif kind == "action":
            actuator = ROS2ActionActuator(item["action"], ros_type, **common)
        else:
            raise ValueError(f"unknown ROS2 effector kind {kind!r}")
        actuators[item["command"]] = actuator
    return BridgePorts(SensorGroup(sensors), ActionRouter(actuators, stop))
