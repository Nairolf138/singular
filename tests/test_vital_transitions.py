from singular.life.vital import compute_vital_timeline
from singular.life.health import ViabilityDriftDetector


def test_viability_drift_escalates_and_recovers_with_hysteresis() -> None:
    detector = ViabilityDriftDetector()
    healthy = {"health": .9, "risk": .05, "resources": .9, "failure_rate": .05,
               "traits": .9, "useful_skills": .9, "fitness": .9}
    degraded = {"health": .1, "risk": .9, "resources": .1, "failure_rate": .9,
                "traits": .2, "useful_skills": .2, "fitness": .1}
    transitions = []
    for metrics in [healthy] * 12 + [degraded] * 14 + [healthy] * 30:
        action, transition = detector.observe(metrics)
        if transition:
            transitions.append((action, transition))
    assert transitions == [
        ("throttled", "drift"), ("paused", "drift"),
        ("restored", "drift"), ("operator", "drift"),
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



def test_vital_budget_exhaustion_is_not_extinction_marker(tmp_path) -> None:
    from singular.life.life_status import LifeStatus, compute_life_status

    mem = tmp_path / "mem"
    mem.mkdir()
    (mem / "world_state.json").write_text('{"global_health":{"score":80}}', encoding="utf-8")
    (mem / "self_narrative.json").write_text('{"identity":{"name":"Alpha","slug":"alpha"}}', encoding="utf-8")
    (mem / "quests_state.json").write_text('{}', encoding="utf-8")

    result = compute_life_status(tmp_path, registry_entry={"status": "active"}, runs=[{"event": "loop.budget_exhausted", "voluntary_budget": True}])

    assert result.status == LifeStatus.BUDGET_EXHAUSTED
    assert result.evidence["vital_timeline"]["state"] != "extinct"
