from __future__ import annotations

import sys
from types import SimpleNamespace

from singular.embodiment import (
    Command,
    ErrorCode,
    ROS2PublisherActuator,
    ROS2Sensor,
    ROS2ServiceActuator,
)


class Message:
    __slots__ = ("command_id", "value", "nested")

    def __init__(self):
        self.command_id = ""
        self.value = 0
        self.nested = SimpleNamespace(x=1)


class Future:
    def __init__(self, result=None, done=True):
        self._result, self._done = result, done

    def done(self):
        return self._done

    def exception(self):
        return None

    def result(self):
        return self._result


class Service:
    Request = Message


class Client:
    available = True
    future = Future(SimpleNamespace(applied=True))

    def wait_for_service(self, timeout_sec):
        return self.available

    def call_async(self, request):
        self.request = request
        return self.future


class Publisher:
    def __init__(self):
        self.messages = []

    def publish(self, message):
        self.messages.append(message)


class Node:
    def __init__(self):
        self.subscriptions = []
        self.publisher = Publisher()
        self.client = Client()
        self.destroyed = False

    def create_subscription(self, typ, topic, callback, qos):
        sub = SimpleNamespace(callback=callback, topic=topic)
        self.subscriptions.append(sub)
        return sub

    def destroy_subscription(self, sub):
        self.subscriptions.remove(sub)

    def create_publisher(self, typ, topic, qos):
        return self.publisher

    def create_client(self, typ, name):
        return self.client

    def destroy_node(self):
        self.destroyed = True


class FakeRclpy:
    def __init__(self):
        self.initialized = False
        self.shutdown_called = False
        self.node = Node()
        self.spin_error = None
        self.on_spin = None

    def ok(self):
        return self.initialized

    def init(self, args=None):
        self.initialized = True

    def shutdown(self):
        self.initialized = False
        self.shutdown_called = True

    def create_node(self, name):
        return self.node

    def spin_once(self, node, timeout_sec=0):
        if self.spin_error:
            raise self.spin_error
        if self.on_spin:
            self.on_spin()

    def spin_until_future_complete(self, node, future, timeout_sec):
        pass


def install_ros(monkeypatch):
    ros = FakeRclpy()
    monkeypatch.setitem(sys.modules, "rclpy", ros)
    return ros


def test_structured_receive_reconnect_and_owned_context_close(monkeypatch):
    ros = install_ros(monkeypatch)
    sensor = ROS2Sensor("/data", Message)
    message = Message()
    message.value = 42
    sensor._receive(message)
    assert sensor.collect()[0].payload == {
        "command_id": "",
        "value": 42,
        "nested": {"x": 1},
    }
    ros.spin_error = OSError("link lost")
    failed = sensor.collect()[0]
    assert failed.error.code is ErrorCode.UNAVAILABLE
    assert len(ros.node.subscriptions) == 1  # failed subscription was replaced
    sensor.close()
    sensor.close()
    assert ros.node.destroyed and ros.shutdown_called


def test_external_node_is_not_destroyed_and_context_is_not_shutdown(monkeypatch):
    ros = install_ros(monkeypatch)
    ros.initialized = True
    node = Node()
    sensor = ROS2Sensor("/data", Message, node=node)
    sensor.close()
    assert not node.destroyed and not ros.shutdown_called


def test_publication_correlates_ack_and_preserves_command_id(monkeypatch):
    ros = install_ros(monkeypatch)
    actuator = ROS2PublisherActuator(
        "/cmd", Message, acknowledgement_topic="/ack", acknowledgement_type=Message
    )
    command = Command("move", {"value": 7})

    def acknowledge():
        ack = Message()
        ack.command_id = command.command_id
        ack.value = 6
        actuator._ack(ack)
        ros.on_spin = None

    ros.on_spin = acknowledge
    result = actuator.execute(command)
    assert result.success and result.command_id == command.command_id
    assert result.actual["value"] == 6
    assert ros.node.publisher.messages[0].value == 7


def test_publication_timeout_and_latched_emergency_stop(monkeypatch):
    install_ros(monkeypatch)
    actuator = ROS2PublisherActuator(
        "/cmd",
        Message,
        timeout_s=0,
        acknowledgement_topic="/ack",
        acknowledgement_type=Message,
    )
    timed_out = actuator.execute(Command("move"))
    assert timed_out.error == ErrorCode.TIMEOUT.value
    actuator.emergency_stop("operator")
    blocked = actuator.execute(Command("move"))
    assert blocked.error == ErrorCode.EMERGENCY_STOP.value


def test_service_actual_and_unavailability(monkeypatch):
    ros = install_ros(monkeypatch)
    actuator = ROS2ServiceActuator("/apply", Service)
    command = Command("apply", {"value": 9})
    result = actuator.execute(command)
    assert result.command_id == command.command_id and result.actual == {
        "applied": True
    }
    ros.node.client.available = False
    assert actuator.execute(command).error == ErrorCode.UNAVAILABLE.value
