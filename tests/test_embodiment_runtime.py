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
from singular.core.agent_runtime import AgentRuntime, Intent
from singular.identity.consolidation_coordinator import ConsolidationCoordinator
from singular.memory_layers import (
    EmbodimentOutcomePipeline,
    LocalJsonMemoryBackend,
    MemoryLayerService,
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


def test_embodied_outcome_is_consolidated_narrated_and_influences_next_decision(
    tmp_path,
) -> None:
    class Perception:
        def collect(self):
            from singular.embodiment import Observation

            return [Observation("range", {"distance": 1}, "range-sensor")]

    class Mind:
        contexts = []

        def propose_intent(self, percept):
            context = percept.payload.get("embodied_memory_context")
            self.contexts.append(context)
            goal = "avoid-obstacle" if context else "approach-obstacle"
            return Intent(goal=goal, rationale="measured feedback", confidence=0.9)

        def propose_action(self, intent, percept):
            return Command(
                "motor.stop" if intent.goal == "avoid-obstacle" else "motor.move",
                {"distance": percept.payload["distance"]},
                intent_goal=intent.goal,
            )

    class Action:
        def execute(self, request):
            from singular.embodiment import Acknowledgement

            return Acknowledgement(
                request.action_type,
                True,
                "obstacle reached",
                command_id=request.command_id,
                actual={"executed": True, "distance": 1},
            )

    mem = tmp_path / "mem"
    memory = MemoryLayerService(LocalJsonMemoryBackend(mem / "layers"))
    pipeline = EmbodimentOutcomePipeline(
        memory, ConsolidationCoordinator(mem), mem / "self_narrative.json"
    )
    mind = Mind()
    runtime = AgentRuntime(
        perception=Perception(), mind=mind, action=Action(), outcome_pipeline=pipeline
    )

    first = runtime.step()[0]
    second = runtime.step()[0]

    assert first.action_type == "motor.move" and first.success
    assert second.action_type == "motor.stop" and second.success
    assert mind.contexts[0] is None
    assert mind.contexts[1]["provenance"][0].startswith("causal:")
    trace_id = mind.contexts[1]["outcomes"][0]["trace_id"]
    assert trace_id
    narrative = json.loads((mem / "self_narrative.json").read_text())
    assert any(
        "motor.move" in item
        for item in narrative["regrets_and_pride"]["significant_successes"]
    )
    audit = json.loads((mem / "consolidation_audit.json").read_text())
    assert any(trace_id in row["provenance"] for row in audit.values())


def test_dry_run_trace_is_not_learned_as_executed_outcome(tmp_path) -> None:
    memory = MemoryLayerService(LocalJsonMemoryBackend(tmp_path / "layers"))
    pipeline = EmbodimentOutcomePipeline(
        memory, ConsolidationCoordinator(tmp_path), tmp_path / "self_narrative.json"
    )

    assert pipeline.consume({"trace_id": "simulation", "dry_run": True}) is None
    assert memory.embodied_outcomes() == []
    assert not (tmp_path / "self_narrative.json").exists()
