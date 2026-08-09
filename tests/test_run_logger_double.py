"""Contract tests for the life-loop logger double."""

from tests.run_logger_double import RecordingRunLogger


def test_recording_run_logger_implements_life_loop_contract():
    logger = RecordingRunLogger("contract-run")

    methods_used_by_life_loop = {
        "log",
        "log_absurde",
        "log_consciousness",
        "log_death",
        "log_delay",
        "log_event",
        "log_interaction",
        "log_phase_metrics",
        "log_refusal",
        "log_test_coevolution",
        "skill_reputation",
    }

    assert logger.run_id == "contract-run"
    assert all(
        callable(getattr(logger, method, None)) for method in methods_used_by_life_loop
    )
    assert logger.__enter__() is logger
    assert logger.__exit__(None, None, None) is False


def test_recording_run_logger_keeps_events_in_memory():
    logger = RecordingRunLogger("in-memory-run")

    logger.log_event("skill.quarantined", skill="unsafe.py")
    logger.log_interaction("memory.recalled", count=2)
    logger.log_death("energy_depleted", age=12)

    assert logger.calls == [
        {
            "method": "log_event",
            "args": ("skill.quarantined",),
            "kwargs": {"skill": "unsafe.py"},
        },
        {
            "method": "log_interaction",
            "args": ("memory.recalled",),
            "kwargs": {"count": 2},
        },
        {
            "method": "log_death",
            "args": ("energy_depleted",),
            "kwargs": {"age": 12},
        },
    ]
