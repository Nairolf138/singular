"""Optional hardware adapters.

ROS imports deliberately happen at construction time so installing Singular does
not imply that a ROS installation (or robot) is present.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
import time
from typing import Any, Callable, Mapping

from .contracts import (
    Acknowledgement,
    Command,
    EmbodimentError,
    EmergencyStop,
    ErrorCode,
    Observation,
    utc_now,
)


class OptionalAdapterUnavailable(RuntimeError):
    pass


def serialize_ros_message(value: Any) -> Any:
    """Turn a ROS message into JSON-compatible, structured Python values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return list(value)
    if isinstance(value, Mapping):
        return {str(k): serialize_ros_message(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize_ros_message(v) for v in value]
    if is_dataclass(value):
        return {
            f.name: serialize_ros_message(getattr(value, f.name)) for f in fields(value)
        }
    getter = getattr(value, "get_fields_and_field_types", None)
    if callable(getter):
        return {name: serialize_ros_message(getattr(value, name)) for name in getter()}
    slots = getattr(value, "__slots__", ())
    if slots:
        return {
            name.lstrip("_"): serialize_ros_message(getattr(value, name))
            for name in slots
            if hasattr(value, name)
        }
    if hasattr(value, "__dict__"):
        return {
            k.lstrip("_"): serialize_ros_message(v)
            for k, v in vars(value).items()
            if not k.startswith("__")
        }
    return str(value)


def populate_ros_message(message: Any, payload: Mapping[str, Any]) -> Any:
    """Recursively populate a request/message instance from a payload mapping."""
    for key, value in payload.items():
        if not hasattr(message, key):
            raise ValueError(f"ROS message has no field {key!r}")
        current = getattr(message, key)
        if isinstance(value, Mapping) and not isinstance(current, Mapping):
            populate_ros_message(current, value)
        else:
            setattr(message, key, value)
    return message


@dataclass(frozen=True)
class ROS2QoS:
    depth: int = 10
    reliability: str | None = None
    durability: str | None = None
    history: str | None = None

    def build(self, rclpy: Any) -> Any:
        """Build a QoSProfile when available, otherwise retain depth semantics."""
        try:
            qos = rclpy.qos
            kwargs: dict[str, Any] = {"depth": self.depth}
            for name, enum_name in (
                ("reliability", "QoSReliabilityPolicy"),
                ("durability", "QoSDurabilityPolicy"),
                ("history", "QoSHistoryPolicy"),
            ):
                configured = getattr(self, name)
                if configured:
                    kwargs[name] = getattr(getattr(qos, enum_name), configured.upper())
            return qos.QoSProfile(**kwargs)
        except (AttributeError, TypeError):
            return self.depth


class _ROS2Endpoint:
    def _start(self, node_name: str, node: Any | None = None) -> None:
        try:
            import rclpy
        except ImportError as exc:
            raise OptionalAdapterUnavailable(
                "ROS2 adapter requires rclpy and a sourced ROS2 environment"
            ) from exc
        self._rclpy = rclpy
        self._closed = False
        self._owns_context = False
        if node is None:
            ok = getattr(rclpy, "ok", lambda: False)()
            if not ok:
                rclpy.init(args=None)
                self._owns_context = True
            self._node = rclpy.create_node(node_name)
            self._owns_node = True
        else:
            self._node = node
            self._owns_node = False

    def _spin_future(self, future: Any, timeout: float) -> Any:
        self._rclpy.spin_until_future_complete(self._node, future, timeout_sec=timeout)
        if not future.done():
            raise TimeoutError(f"ROS2 operation timed out after {timeout}s")
        exception = getattr(future, "exception", lambda: None)()
        if exception:
            raise exception
        return future.result()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._owns_node:
            self._node.destroy_node()
        if self._owns_context and getattr(self._rclpy, "ok", lambda: True)():
            self._rclpy.shutdown()


@dataclass
class ROS2Sensor(_ROS2Endpoint):
    topic: str
    message_type: Any
    node_name: str = "singular_sensor"
    qos: ROS2QoS = field(default_factory=ROS2QoS)
    timeout_s: float = 0.0
    reconnect: bool = True
    transform: Callable[[dict[str, Any]], dict[str, Any]] = lambda payload: payload
    node: Any | None = None

    def __post_init__(self) -> None:
        self._start(self.node_name, self.node)
        self._pending: list[Observation] = []
        self._connect()

    def _connect(self) -> None:
        self._subscription = self._node.create_subscription(
            self.message_type, self.topic, self._receive, self.qos.build(self._rclpy)
        )

    def _receive(self, message: Any) -> None:
        payload = serialize_ros_message(message)
        if not isinstance(payload, dict):
            payload = {"value": payload}
        self._pending.append(
            Observation("ros2", self.transform(payload), f"ros2:{self.topic}")
        )

    def collect(self) -> list[Observation]:
        try:
            self._rclpy.spin_once(self._node, timeout_sec=self.timeout_s)
        except Exception as exc:
            if self.reconnect:
                try:
                    destroy = getattr(self._node, "destroy_subscription", None)
                    if callable(destroy):
                        destroy(self._subscription)
                    self._connect()
                except Exception:
                    pass
            return [
                Observation(
                    "ros2.error",
                    {},
                    f"ros2:{self.topic}",
                    error=EmbodimentError(ErrorCode.UNAVAILABLE, str(exc)),
                )
            ]
        result, self._pending = self._pending, []
        return result


class _ROS2Actuator(_ROS2Endpoint):
    def __init__(
        self,
        *,
        node_name: str,
        timeout_s: float,
        node: Any | None,
        stop: EmergencyStop | None,
    ) -> None:
        self.timeout_s = timeout_s
        self.stop = stop or EmergencyStop()
        self._start(node_name, node)

    def emergency_stop(self, reason: str = "operator_request") -> None:
        self.stop.engage(reason)

    def _blocked(self, command: Command) -> Acknowledgement | None:
        if self.stop.engaged:
            return Acknowledgement(
                command.action_type,
                False,
                "emergency stop engaged",
                ErrorCode.EMERGENCY_STOP.value,
                command_id=command.command_id,
                actual={"reason": self.stop.reason},
            )
        return None

    def _error(self, command: Command, exc: Exception) -> Acknowledgement:
        code = (
            ErrorCode.TIMEOUT
            if isinstance(exc, TimeoutError)
            else ErrorCode.UNAVAILABLE
        )
        return Acknowledgement(
            command.action_type,
            False,
            str(exc),
            code.value,
            command_id=command.command_id,
        )


class ROS2PublisherActuator(_ROS2Actuator):
    """Publish a command and optionally correlate an acknowledgement topic."""

    def __init__(
        self,
        topic: str,
        message_type: Any,
        *,
        qos: ROS2QoS = ROS2QoS(),
        timeout_s: float = 1.0,
        acknowledgement_topic: str | None = None,
        acknowledgement_type: Any | None = None,
        transform: Callable[[Command], Mapping[str, Any]] = lambda c: c.parameters,
        node_name: str = "singular_publisher",
        node: Any | None = None,
        stop: EmergencyStop | None = None,
    ) -> None:
        super().__init__(node_name=node_name, timeout_s=timeout_s, node=node, stop=stop)
        self.topic, self.message_type, self.transform = topic, message_type, transform
        self._publisher = self._node.create_publisher(
            message_type, topic, qos.build(self._rclpy)
        )
        self._acks: dict[str, Any] = {}
        self._ack_subscription = None
        if acknowledgement_topic and acknowledgement_type:
            self._ack_subscription = self._node.create_subscription(
                acknowledgement_type,
                acknowledgement_topic,
                self._ack,
                qos.build(self._rclpy),
            )

    def _ack(self, message: Any) -> None:
        data = serialize_ros_message(message)
        command_id = data.get("command_id") if isinstance(data, dict) else None
        if command_id:
            self._acks[str(command_id)] = data

    def execute(self, command: Command) -> Acknowledgement:
        if blocked := self._blocked(command):
            return blocked
        try:
            message = populate_ros_message(self.message_type(), self.transform(command))
            self._publisher.publish(message)
            if self._ack_subscription:
                deadline = time.monotonic() + self.timeout_s
                while (
                    command.command_id not in self._acks and time.monotonic() < deadline
                ):
                    self._rclpy.spin_once(
                        self._node, timeout_sec=max(0.0, deadline - time.monotonic())
                    )
                if command.command_id not in self._acks:
                    raise TimeoutError(f"no acknowledgement for {command.command_id}")
                actual = self._acks.pop(command.command_id)
            else:
                actual = {
                    "published": serialize_ros_message(message),
                    "topic": self.topic,
                    "published_at": utc_now(),
                }
            return Acknowledgement(
                command.action_type,
                True,
                "ROS2 command acknowledged",
                command_id=command.command_id,
                actual=actual,
            )
        except Exception as exc:
            return self._error(command, exc)


class ROS2ServiceActuator(_ROS2Actuator):
    def __init__(
        self,
        service: str,
        service_type: Any,
        *,
        timeout_s: float = 2.0,
        transform: Callable[[Command], Mapping[str, Any]] = lambda c: c.parameters,
        node_name: str = "singular_service",
        node: Any | None = None,
        stop: EmergencyStop | None = None,
    ) -> None:
        super().__init__(node_name=node_name, timeout_s=timeout_s, node=node, stop=stop)
        self.service, self.service_type, self.transform = (
            service,
            service_type,
            transform,
        )
        self._client = self._node.create_client(service_type, service)

    def execute(self, command: Command) -> Acknowledgement:
        if blocked := self._blocked(command):
            return blocked
        try:
            if not self._client.wait_for_service(timeout_sec=self.timeout_s):
                raise RuntimeError(f"service {self.service!r} unavailable")
            request = populate_ros_message(
                self.service_type.Request(), self.transform(command)
            )
            actual = serialize_ros_message(
                self._spin_future(self._client.call_async(request), self.timeout_s)
            )
            return Acknowledgement(
                command.action_type,
                True,
                "ROS2 service completed",
                command_id=command.command_id,
                actual=actual if isinstance(actual, dict) else {"value": actual},
            )
        except Exception as exc:
            return self._error(command, exc)


class ROS2ActionActuator(_ROS2Actuator):
    def __init__(
        self,
        action: str,
        action_type: Any,
        *,
        timeout_s: float = 5.0,
        transform: Callable[[Command], Mapping[str, Any]] = lambda c: c.parameters,
        node_name: str = "singular_action",
        node: Any | None = None,
        stop: EmergencyStop | None = None,
        action_client_factory: Callable[..., Any] | None = None,
    ) -> None:
        super().__init__(node_name=node_name, timeout_s=timeout_s, node=node, stop=stop)
        if action_client_factory is None:
            from rclpy.action import ActionClient

            action_client_factory = ActionClient
        self.action, self.action_type, self.transform = action, action_type, transform
        self._client = action_client_factory(self._node, action_type, action)

    def execute(self, command: Command) -> Acknowledgement:
        if blocked := self._blocked(command):
            return blocked
        try:
            if not self._client.wait_for_server(timeout_sec=self.timeout_s):
                raise RuntimeError(f"action {self.action!r} unavailable")
            goal = populate_ros_message(
                self.action_type.Goal(), self.transform(command)
            )
            handle = self._spin_future(
                self._client.send_goal_async(goal), self.timeout_s
            )
            if not handle.accepted:
                return Acknowledgement(
                    command.action_type,
                    False,
                    "goal refused",
                    ErrorCode.REFUSED.value,
                    command_id=command.command_id,
                )
            wrapped = self._spin_future(handle.get_result_async(), self.timeout_s)
            result = getattr(wrapped, "result", wrapped)
            actual = serialize_ros_message(result)
            return Acknowledgement(
                command.action_type,
                True,
                "ROS2 action completed",
                command_id=command.command_id,
                actual=actual if isinstance(actual, dict) else {"value": actual},
            )
        except Exception as exc:
            return self._error(command, exc)


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
        self._device, self._stopped = OutputDevice(self.pin), False

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
