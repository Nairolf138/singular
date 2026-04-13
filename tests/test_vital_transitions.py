from singular.life.vital import compute_vital_timeline


def test_vital_transition_to_declining_on_age_threshold() -> None:
    payload = compute_vital_timeline(
        age=50,
        current_health=80.0,
        failure_rate=0.2,
        failure_streak=0,
        extinction_seen=False,
    )
    assert payload["state"] == "declining"
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
    )
    assert payload["state"] == "extinct"
    assert payload["risk_level"] == "high"
    assert payload["causes"] == ["extinction_observed"]


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

