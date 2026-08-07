from __future__ import annotations

import json

from singular.learning import FeedbackEvent, LearningOrchestrator, LearningPolicy


POLICY = LearningPolicy(minimum_evidence=2, minimum_distinct_sources=2)


def event(source: str, reward: float, *, event_id: str, life_id: str = "one") -> FeedbackEvent:
    return FeedbackEvent(source, "route", reward, {"domain": "test"}, event_id=event_id, life_id=life_id)


def ready(tmp_path, *, evaluator=None) -> LearningOrchestrator:
    learner = LearningOrchestrator(tmp_path, life_id="one", policy=POLICY, evaluator=evaluator)
    learner.add_regression_case("known", {"prompt": "1+1"}, 2)
    return learner


def test_incremental_feedback_stays_candidate_until_evidence_threshold(tmp_path):
    learner = ready(tmp_path)
    candidate = learner.ingest(event("run", 0.3, event_id="a"), kind="strategy", proposed_value="careful")
    assert not learner.evaluate_and_promote(candidate).activated
    learner.ingest(event("conversation", 0.4, event_id="b"), kind="strategy", proposed_value="careful")
    assert learner.evaluate_and_promote(candidate).activated
    assert learner.metrics()["retention_30d_pct"] == 100.0


def test_contradictory_feedback_blocks_activation(tmp_path):
    learner = ready(tmp_path)
    candidate = learner.ingest(event("run", 0.8, event_id="a"), kind="strategy", proposed_value="fast")
    learner.ingest(event("action", 0.8, event_id="b"), kind="strategy", proposed_value="slow")
    decision = learner.evaluate_and_promote(candidate)
    assert not decision.activated
    assert "contradictory_feedback" in decision.reason


def test_rollback_restores_previous_active_version(tmp_path):
    learner = ready(tmp_path)
    candidate = learner.ingest(event("run", 0.2, event_id="a"), kind="strategy", proposed_value="v1")
    learner.ingest(event("action", 0.2, event_id="b"), kind="strategy", proposed_value="v1")
    assert learner.evaluate_and_promote(candidate).activated
    assert learner.rollback(key="strategy:route")
    state = json.loads(learner.state_path.read_text())
    assert "strategy:route" not in state["active"]


def test_drift_and_forgetting_protection_reject_candidate(tmp_path):
    learner = ready(tmp_path, evaluator=lambda *_: {"gain": .2, "retention": .4, "regression": .2})
    candidate = learner.ingest(event("run", -0.4, event_id="a"), kind="skill", proposed_value={"reliability": .8})
    learner.ingest(event("social", 0.8, event_id="b"), kind="skill", proposed_value={"reliability": .8})
    decision = learner.evaluate_and_promote(candidate)
    assert not decision.activated
    assert "drift_detected" in decision.reason
    assert "catastrophic_forgetting_risk" in decision.reason


def test_lives_are_isolated(tmp_path):
    first = ready(tmp_path)
    second = LearningOrchestrator(tmp_path, life_id="two", policy=POLICY)
    first.ingest(event("run", .1, event_id="shared"), kind="belief", proposed_value=True)
    second.ingest(event("run", .1, event_id="shared", life_id="two"), kind="belief", proposed_value=True)
    assert first.state_path != second.state_path
    assert json.loads(first.state_path.read_text())["events"].keys() == json.loads(second.state_path.read_text())["events"].keys()


def test_interrupted_transaction_is_recovered(tmp_path):
    learner = ready(tmp_path)
    recovered = learner._empty_state()
    recovered["version"] = 9
    learner._write(learner.journal_path, {"prepared_at": "now", "state": recovered})
    restarted = LearningOrchestrator(tmp_path, life_id="one", policy=POLICY)
    assert json.loads(restarted.state_path.read_text())["version"] == 9
    assert not restarted.journal_path.exists()
