from __future__ import annotations

import json

from singular import cli
from singular.embodiment import (
    ActuatorSimulator,
    Command,
    EmbodimentRuntime,
    ErrorCode,
    ScriptedSensor,
)


def test_multiple_sensors_effectors_and_measured_feedback() -> None:
    events = []
    motor = ActuatorSimulator()
    speaker = ActuatorSimulator()
    runtime = EmbodimentRuntime(
        {
            "camera": ScriptedSensor("camera", "vision", [{"target": "left"}]),
            "microphone": ScriptedSensor("microphone", "audio", [{"text": "go"}]),
        },
        {"motor.move": motor, "speaker.say": speaker},
        audit_sink=events.append,
    )

    assert {item.event_type for item in runtime.collect()} == {"vision", "audio"}
    move = runtime.execute(Command("motor.move", {"distance": 2}))
    say = runtime.execute(Command("speaker.say", {"text": "ok"}))
    feedback = runtime.collect()

    assert move.success and say.success
    assert motor.commands[0].parameters == {"distance": 2}
    assert speaker.commands[0].parameters == {"text": "ok"}
    assert [item.event_type for item in feedback] == ["action.result", "action.result"]
    assert feedback[0].payload["actual"]["parameters"] == {"distance": 2}
    assert events[-1]["state"]["latest_observations"]
    assert events[-1]["state"]["pending_commands"] == {}


def test_refusal_adapter_failure_emergency_stop_and_deterministic_close() -> None:
    class FailingSensor:
        closed = 0

        def collect(self):
            raise RuntimeError("camera disconnected")

        def close(self):
            self.closed += 1

    sensor = FailingSensor()
    actuator = ActuatorSimulator(refused_actions=frozenset({"motor.move"}))
    runtime = EmbodimentRuntime({"camera": sensor}, {"motor.move": actuator})

    failed = runtime.collect()[0]
    assert failed.error is not None and failed.error.code is ErrorCode.IO_ERROR
    assert runtime.execute(Command("motor.move")).error == ErrorCode.REFUSED.value
    runtime.request_emergency_stop("operator")
    assert (
        runtime.execute(Command("motor.move")).error == ErrorCode.EMERGENCY_STOP.value
    )
    runtime.close()
    runtime.close()

    assert sensor.closed == 1
    assert runtime.state.closed is True
    assert runtime.state.emergency_stop.reason == "operator"
    assert runtime.state.errors[0]["adapter"] == "sensor:camera"


def test_dry_run_does_not_touch_actuator() -> None:
    actuator = ActuatorSimulator()
    runtime = EmbodimentRuntime([], {"motor.move": actuator}, dry_run=True)
    acknowledgement = runtime.execute(Command("motor.move"))
    assert acknowledgement.actual == {"executed": False, "dry_run": True}
    assert actuator.commands == []


def test_cli_runs_simulated_configuration_and_writes_audit(tmp_path, capsys) -> None:
    config = tmp_path / "embodiment.json"
    audit = tmp_path / "audit.jsonl"
    config.write_text(
        json.dumps(
            {
                "steps": 2,
                "sensors": [
                    {"name": "range", "event_type": "range", "readings": [{"cm": 3}]}
                ],
                "effectors": [{"command": "motor.stop"}],
                "rules": [{"event_type": "range", "command": "motor.stop"}],
            }
        ),
        encoding="utf-8",
    )

    assert (
        cli.main(
            [
                "--format",
                "json",
                "embodiment",
                "--config",
                str(config),
                "--audit",
                str(audit),
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["actions"] == 1
    records = [
        json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()
    ]
    assert records[-1]["event"] == "embodiment.closed"
    assert records[-1]["state"]["closed"] is True
