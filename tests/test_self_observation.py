from __future__ import annotations

import json

from singular.cognition.reflect import ActionHypothesis, reflect_action
from singular.cognition.self_observation import SelfObservationService
from singular.identity.self_model import SCHEMA_VERSION, SelfModelStore


def _observation(index: int, *, success: bool, prediction: float = 0.8):
    return {
        "domain": "mutation",
        "prediction": prediction,
        "success": success,
        "error_type": "regression" if not success else None,
        "strategy": "simulate",
        "evidence_refs": [f"trace:{index}"],
    }


def test_schema_migration_and_metacognition_persist(tmp_path):
    path = tmp_path / "self.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "autobiographical_facts": {},
                "traits": {},
                "preferences": {},
                "constraints": {},
            }
        )
    )
    store = SelfModelStore(path)
    service = SelfObservationService(store)
    service.observe([_observation(1, success=True)])

    reloaded = SelfModelStore(path).read()
    assert reloaded["schema_version"] == SCHEMA_VERSION
    assert reloaded["metacognition"]["version"] == 1
    assert reloaded["metacognition"]["domains"]["mutation"]["evidence_refs"] == [
        "trace:1"
    ]


def test_sparse_evidence_stays_uncertain_and_duplicate_reference_is_ignored(tmp_path):
    service = SelfObservationService(tmp_path / "self.json")
    service.observe([_observation(1, success=True, prediction=0.99)])
    model = service.observe([_observation(1, success=True, prediction=0.99)])
    domain = model["metacognition"]["domains"]["mutation"]

    assert domain["sample_count"] == 1
    assert domain["competence"] < 0.7
    assert domain["uncertainty"] == 1.0


def test_calibration_and_repeated_failures_are_evidence_backed(tmp_path):
    service = SelfObservationService(tmp_path / "self.json")
    model = service.observe(
        [_observation(i, success=False, prediction=0.9) for i in range(3)]
    )
    meta = model["metacognition"]
    domain = meta["domains"]["mutation"]

    assert domain["calibration_score"] < 0.55
    assert "repeated_failure:regression" in domain["limitations"]
    assert meta["recurring_errors"]["mutation:regression"]["count"] == 3
    assert len(meta["calibration_history"]) == 3


def test_low_calibration_changes_later_reflection_recommendation(tmp_path):
    service = SelfObservationService(tmp_path / "self.json")
    service.observe([_observation(i, success=False, prediction=0.95) for i in range(3)])
    decision = reflect_action(
        [ActionHypothesis("rewrite", 0.9, 0.1, 0.1)],
        metacognition=service.decision_context("mutation"),
    )

    assert decision.action == "rewrite"
    assert decision.action_recommended == "simulate_or_escalate"
    assert decision.confidence < 0.55
    assert "repeated_failure:regression" in decision.risks
