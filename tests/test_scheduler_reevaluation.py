import time

from singular.agents import Agent
from singular.schedulers import start
from singular.schedulers.reevaluation import alerts_from_records, detect_alerts


def test_scheduler_triggers_goal_reevaluation():
    agent = Agent()
    calls = {"count": 0}

    def spy() -> None:
        calls["count"] += 1

    # Replace choose_goal with spy to count invocations
    agent.choose_goal = spy  # type: ignore[assignment]

    stop_event = start(0.01, agent)
    time.sleep(0.05)
    stop_event.set()

    assert calls["count"] > 0


def test_detect_alerts_thresholds() -> None:
    alerts = detect_alerts(
        health_scores=[80.0, 76.0, 72.0, 68.0, 63.0],
        sandbox_failure_rates=[0.05, 0.1, 0.15, 0.2, 0.1, 0.2, 0.35, 0.4, 0.45, 0.5],
        stagnation_steps=12,
    )
    kinds = {alert.kind for alert in alerts}
    assert "health_decline" in kinds
    assert "sandbox_failures_rising" in kinds
    assert "prolonged_stagnation" in kinds


def test_alerts_from_records_uses_health_and_acceptance() -> None:
    records = [
        {
            "accepted": False,
            "health": {"score": 70.0 - i, "sandbox_stability": 0.95 - (i * 0.04)},
        }
        for i in range(12)
    ]
    alerts = alerts_from_records(records)
    assert {alert["kind"] for alert in alerts} == {
        "health_decline",
        "sandbox_failures_rising",
        "prolonged_stagnation",
    }
