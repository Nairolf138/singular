from pathlib import Path

import pytest

from singular.learning import Demonstration, ImitationEngine


def _event(**overrides):
    payload = {
        "schema_version": 1,
        "is_demonstration": True,
        "observations": [{"signal": "left"}, {"signal": "right"}],
        "actions": ["turn_left", "turn_right"],
        "results": ["safe", "safe"],
        "demonstrator": "human-1",
        "consent": {"granted": True, "scope": "learning"},
        "context": {"environment": "simulator"},
        "provenance": {"session": "verified-1"},
        "safety_constraints": ["never act outside the simulator"],
        "skill": "navigation",
    }
    payload.update(overrides)
    return payload


def test_ordinary_interaction_is_not_silently_ingested(tmp_path: Path) -> None:
    engine = ImitationEngine(tmp_path)
    assert engine.ingest_interaction({"observations": [1], "actions": [2]}) is None
    assert engine.pending == []
    with pytest.raises(ValueError, match="explicit"):
        engine.ingest({"observations": [1], "actions": [2]})


def test_consent_event_survives_restart_and_poisoning_is_rejected(
    tmp_path: Path,
) -> None:
    ImitationEngine(tmp_path).ingest_interaction(_event())
    restarted = ImitationEngine(tmp_path)
    assert restarted.pending[0].name == "navigation"
    with pytest.raises(ValueError, match="conflicting"):
        restarted.ingest_interaction(
            _event(observations=[{"x": 1}, {"x": 1}], actions=["safe", "unsafe"])
        )


def test_sensitive_imitation_requires_approval(tmp_path: Path) -> None:
    engine = ImitationEngine(tmp_path)
    demo = engine.ingest_interaction(
        _event(context={"sensitive_capability": True, "approval": False})
    )
    assert demo is not None
    outcome = engine.evaluate_and_publish(demo, engine.propose_candidate(demo))
    assert outcome.status == "quarantined"
    assert "approval" in outcome.reason


def test_exact_memorizer_fails_independent_heldout_variation(tmp_path: Path) -> None:
    engine = ImitationEngine(tmp_path)
    demo = Demonstration(
        [{"color": "red"}, {"color": "green"}],
        ["stop", "go"],
        "memorizer",
        {
            "heldout": {
                "observations": [{"color": "amber"}, {"color": "blue"}],
                "actions": ["wait", "yield"],
            }
        },
    )
    exact_source = "_P = [({'color': 'red'}, 'stop'), ({'color': 'green'}, 'go')]\ndef run(o):\n    for x, a in _P:\n        if x == o:\n            return a\n    return 'stop'\n"
    assert engine.evaluate_and_publish(demo, exact_source).status == "quarantined"


def test_active_imitation_requests_high_cost_unknown_only(tmp_path: Path) -> None:
    engine = ImitationEngine(tmp_path)
    assert (
        engine.request_if_unknown("surgery", known=False, trial_cost=0.95) is not None
    )
    assert engine.request_if_unknown("sorting", known=False, trial_cost=0.1) is None
    assert engine.request_if_unknown("known", known=True, trial_cost=1.0) is None
