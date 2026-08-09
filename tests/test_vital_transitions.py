import pytest

from singular.life.health import ViabilityDriftDetector
from singular.life.vital import VitalState, VitalStateMachine, compute_vital_timeline


def test_viability_drift_escalates_and_recovers_with_hysteresis() -> None:
    detector = ViabilityDriftDetector()
    healthy = {
        "health": 0.9,
        "risk": 0.05,
        "resources": 0.9,
        "failure_rate": 0.05,
        "traits": 0.9,
        "useful_skills": 0.9,
        "fitness": 0.9,
    }
    degraded = {
        "health": 0.1,
        "risk": 0.9,
        "resources": 0.1,
        "failure_rate": 0.9,
        "traits": 0.2,
        "useful_skills": 0.2,
        "fitness": 0.1,
    }
    transitions = []
    for metrics in [healthy] * 12 + [degraded] * 14 + [healthy] * 30:
        action, transition = detector.observe(metrics)
        if transition:
            transitions.append((action, transition))
    assert transitions == [
        ("throttled", "drift"),
        ("paused", "drift"),
        ("restored", "drift"),
        ("operator", "drift"),
        ("normal", "recovered"),
    ]


def test_vital_transition_to_declining_on_age_threshold() -> None:
    payload = compute_vital_timeline(
        age=50,
        current_health=80.0,
        failure_rate=0.2,
        failure_streak=0,
        extinction_seen=False,
    )
    assert payload["state"] == "at_risk"
    assert "age_decline_threshold" in payload["causes"]


def test_vital_transition_to_terminal_on_failure_streak() -> None:
    payload = compute_vital_timeline(
        age=20,
        current_health=70.0,
        failure_rate=0.4,
        failure_streak=5,
        extinction_seen=False,
    )
    assert payload["state"] == "terminal"
    assert payload["terminal"] is True
    assert "failure_streak" in payload["causes"]


def test_vital_transition_to_extinct_preempts_other_states() -> None:
    payload = compute_vital_timeline(
        age=1,
        current_health=99.0,
        failure_rate=0.0,
        failure_streak=0,
        extinction_seen=True,
        registry_status="extinct",
        extinction_duration=3,
    )
    assert payload["state"] == "extinct"
    assert payload["risk_level"] == "high"
    assert payload["causes"] == ["sustained_concordant_extinction_evidence"]


@pytest.mark.parametrize("name", ["Ada", "Bob", "Eve"])
def test_named_lives_follow_deterministic_audited_trajectory(name: str) -> None:
    life = VitalStateMachine()
    assert (
        life.transition(VitalState.AT_RISK, cause=f"{name}:resource_loss")
        == VitalState.AT_RISK
    )
    assert (
        life.transition(VitalState.CRITICAL, cause="sustained_failure")
        == VitalState.CRITICAL
    )
    life.record_rescue("recovery_quest")
    life.record_rescue("healthy_checkpoint_search")
    assert (
        life.transition(VitalState.TERMINAL, cause="rescue_exhausted")
        == VitalState.TERMINAL
    )
    assert (
        life.transition(VitalState.DEAD, cause="resources_exhausted") == VitalState.DEAD
    )
    assert (
        life.transition(VitalState.EXTINCT, cause="concordant_evidence")
        == VitalState.EXTINCT
    )
    assert life.audit() == {
        "root_cause": f"{name}:resource_loss",
        "rescue_attempts": ["recovery_quest", "healthy_checkpoint_search"],
        "last_irreversible_decision": "dead->extinct:concordant_evidence",
    }


def test_single_extinction_signal_is_not_irreversible() -> None:
    payload = compute_vital_timeline(
        age=1,
        current_health=99,
        failure_rate=0,
        failure_streak=0,
        extinction_seen=True,
        extinction_duration=99,
    )
    assert payload["state"] == "stable"
    assert payload["extinction_evidence"]["confirmed"] is False


def test_vital_reproduction_window_boundary_conditions() -> None:
    too_young = compute_vital_timeline(
        age=2,
        current_health=80.0,
        failure_rate=0.2,
        failure_streak=0,
        extinction_seen=False,
    )
    eligible = compute_vital_timeline(
        age=3,
        current_health=80.0,
        failure_rate=0.2,
        failure_streak=0,
        extinction_seen=False,
    )
    too_old = compute_vital_timeline(
        age=81,
        current_health=80.0,
        failure_rate=0.2,
        failure_streak=0,
        extinction_seen=False,
    )
    assert too_young["reproduction_eligible"] is False
    assert eligible["reproduction_eligible"] is True
    assert too_old["reproduction_eligible"] is False


def test_vital_budget_exhaustion_is_not_extinction_marker(tmp_path) -> None:
    from singular.life.life_status import LifeStatus, compute_life_status

    mem = tmp_path / "mem"
    mem.mkdir()
    (mem / "world_state.json").write_text(
        '{"global_health":{"score":80}}', encoding="utf-8"
    )
    (mem / "self_narrative.json").write_text(
        '{"identity":{"name":"Alpha","slug":"alpha"}}', encoding="utf-8"
    )
    (mem / "quests_state.json").write_text("{}", encoding="utf-8")

    result = compute_life_status(
        tmp_path,
        registry_entry={"status": "active"},
        runs=[{"event": "loop.budget_exhausted", "voluntary_budget": True}],
    )

    assert result.status == LifeStatus.BUDGET_EXHAUSTED
    assert result.evidence["vital_timeline"]["state"] != "extinct"
