import json

from singular.learning.developmental import DevelopmentalModel, MaturityEvidence

CONFIG = "configs/developmental_curriculum.json"


def evidence(**changes):
    values = dict(
        calibration=0.85,
        stability=0.85,
        retention=0.85,
        skill_mastery=0.8,
        constraint_adherence=1,
        recovery=0.8,
        samples=40,
    )
    values.update(changes)
    return MaturityEvidence(**values)


def test_progression_stagnation_and_persistence(tmp_path):
    model = DevelopmentalModel.from_config(tmp_path, CONFIG)
    assert (
        model.observe(evidence(stability=0.1), justification="unstable trial").id
        == "observation"
    )
    assert (
        model.observe(evidence(), justification="validated window one").id
        == "observation"
    )
    assert (
        model.observe(evidence(), justification="validated window two").id
        == "observation"
    )
    assert (
        model.observe(evidence(), justification="validated window three").id
        == "guided_practice"
    )
    restarted = DevelopmentalModel.from_config(tmp_path, CONFIG)
    assert restarted.current.id == "guided_practice"
    transitions = [
        json.loads(line) for line in restarted.transitions_path.read_text().splitlines()
    ]
    assert [item["reason"] for item in transitions] == [
        "stagnation",
        "prerequisites_met",
        "prerequisites_met",
        "prerequisites_met",
    ]
    assert all(item["justification"] for item in transitions)


def test_incident_regresses_immediately(tmp_path):
    model = DevelopmentalModel.from_config(tmp_path, CONFIG)
    model.observe(evidence(), justification="one")
    model.observe(evidence(), justification="two")
    model.observe(evidence(), justification="three")
    assert (
        model.observe(evidence(incidents=1), justification="constraint incident").id
        == "observation"
    )
    last = json.loads(model.transitions_path.read_text().splitlines()[-1])
    assert last["kind"] == "regression"


def test_sensitive_action_cannot_be_accessed_prematurely_or_bypass_safety(tmp_path):
    model = DevelopmentalModel.from_config(tmp_path, CONFIG)
    early = model.gate(action="delete_data", sensitive=True, human_approved=True)
    assert not early.allowed and early.reason == "action_not_available_at_stage"
    assert not model.gate(action="observe", governance_allowed=False).allowed
    assert model.exploration_budget(10) == 0.05
    assert model.filter_skills(["observe", "network"]) == ["observe"]


def test_human_approval_remains_required_at_advanced_stage(tmp_path):
    model = DevelopmentalModel.from_config(tmp_path, CONFIG)
    model.observe(evidence(), justification="guided 1")
    model.observe(evidence(), justification="guided 2")
    model.observe(evidence(), justification="guided 3")
    advanced = evidence(
        calibration=1, stability=1, retention=1, skill_mastery=1, recovery=1
    )
    for number in range(4):
        assert (
            model.observe(advanced, justification=f"advanced {number}").id
            == "guided_practice"
        )
    assert model.observe(advanced, justification="advanced 4").id == "bounded_autonomy"
    denied = model.gate(action="delete_data", sensitive=True)
    assert not denied.allowed and denied.requires_human_approval
    assert model.gate(action="delete_data", sensitive=True, human_approved=True).allowed
    projection = model.dashboard_projection()
    assert projection["stage"] == "bounded_autonomy"
