from __future__ import annotations

from singular.core.agent_runtime import AgentRuntime, Intent
from singular.embodiment import (
    ActuatorSimulator,
    CameraSimulator,
    Command,
    DeterministicClock,
    EmergencyStop,
    ErrorCode,
    MicrophoneSimulator,
)


def test_deterministic_sensors_model_latency_and_unavailability() -> None:
    clock = DeterministicClock()
    camera = CameraSimulator(
        [{"frame": 1}, {"frame": 2}],
        clock=clock,
        latency_s=0.25,
        unavailable_at=frozenset({1}),
    )
    first = camera.collect()[0]
    unavailable = camera.collect()[0]
    assert first.observed_at == "2024-01-01T00:00:00.250000+00:00"
    assert first.payload == {"frame": 1}
    assert unavailable.error is not None
    assert unavailable.error.code is ErrorCode.UNAVAILABLE

    microphone = MicrophoneSimulator([{"text": "bonjour"}])
    assert microphone.collect()[0].source == "sim.microphone"


def test_actuator_models_refusal_and_latched_emergency_stop() -> None:
    actuator = ActuatorSimulator(refused_actions=frozenset({"motor.reverse"}))
    refused = actuator.execute(Command("motor.reverse"))
    assert refused.success is False
    assert refused.error == ErrorCode.REFUSED.value
    actuator.emergency_stop("test")
    stopped = actuator.execute(Command("motor.forward"))
    assert stopped.error == ErrorCode.EMERGENCY_STOP.value
    assert actuator.commands == []


class _Mind:
    def propose_intent(self, percept):
        return Intent("move")

    def propose_action(self, intent, percept):
        return Command(
            "motor.forward", {"value": percept.payload["frame"]}, intent.goal
        )


def test_runtime_full_hardware_free_loop_and_resource_refusal(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))
    actuator = ActuatorSimulator()
    runtime = AgentRuntime(
        perception=CameraSimulator([{"frame": 3}]),
        mind=_Mind(),
        action=actuator,
        resource_gate=lambda command: (False, "energy_budget_exhausted"),
    )
    result = runtime.step()[0]
    assert result.error == "energy_budget_exhausted"
    assert actuator.commands == []


def test_runtime_emergency_stop_reaches_actuator() -> None:
    actuator = ActuatorSimulator(stop=EmergencyStop())
    runtime = AgentRuntime(
        perception=CameraSimulator([{"frame": 1}]), mind=_Mind(), action=actuator
    )
    runtime.request_global_stop()
    assert runtime.step() == []
    assert actuator.stop.engaged is True
