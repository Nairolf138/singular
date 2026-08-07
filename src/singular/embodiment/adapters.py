"""Optional ROS2 and GPIO adapters; imports occur only when instantiated."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .contracts import Acknowledgement, Command, Observation, utc_now


class OptionalAdapterUnavailable(RuntimeError):
    pass


@dataclass
class ROS2Sensor:
    topic: str
    message_type: Any
    node_name: str = "singular_sensor"

    def __post_init__(self) -> None:
        try:
            import rclpy
        except ImportError as exc:
            raise OptionalAdapterUnavailable(
                "ROS2 adapter requires the 'ros2' extra (rclpy)"
            ) from exc
        self._rclpy = rclpy
        rclpy.init(args=None)
        self._node = rclpy.create_node(self.node_name)
        self._pending: list[Observation] = []
        self._subscription = self._node.create_subscription(
            self.message_type, self.topic, self._receive, 10
        )

    def _receive(self, message: Any) -> None:
        payload = message if isinstance(message, dict) else {"message": str(message)}
        self._pending.append(Observation("ros2", payload, f"ros2:{self.topic}"))

    def collect(self) -> list[Observation]:
        self._rclpy.spin_once(self._node, timeout_sec=0.0)
        result, self._pending = self._pending, []
        return result

    def close(self) -> None:
        self._node.destroy_node()


@dataclass
class GPIOActuator:
    pin: int
    transform: Callable[[Command], bool] = lambda command: bool(
        command.parameters.get("value", True)
    )

    def __post_init__(self) -> None:
        try:
            from gpiozero import OutputDevice
        except ImportError as exc:
            raise OptionalAdapterUnavailable(
                "GPIO adapter requires the 'gpio' extra (gpiozero)"
            ) from exc
        self._device = OutputDevice(self.pin)
        self._stopped = False

    def execute(self, command: Command) -> Acknowledgement:
        if self._stopped:
            return Acknowledgement(
                command.action_type,
                False,
                "emergency stop engaged",
                "emergency_stop",
                command_id=command.command_id,
            )
        value = self.transform(command)
        self._device.on() if value else self._device.off()
        return Acknowledgement(
            command.action_type,
            True,
            "gpio updated",
            command_id=command.command_id,
            actual={"pin": self.pin, "value": value, "observed_at": utc_now()},
        )

    def emergency_stop(self, reason: str = "operator_request") -> None:
        self._stopped = True
        self._device.off()
