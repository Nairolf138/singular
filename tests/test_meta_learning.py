from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from singular.beliefs.meta_learning import (
    extract_run_features,
    recommend_strategy,
    register_run_result,
)
from singular.beliefs.store import BeliefStore


def test_meta_learning_converges_to_best_operator(tmp_path: Path) -> None:
    store = BeliefStore(path=tmp_path / "beliefs.json")
    for _ in range(8):
        register_run_result(
            store,
            extract_run_features(
                operator="eq_rewrite_reduce_sum",
                accepted=True,
                base_score=1.0,
                mutated_score=0.8,
                temperature=20.0,
                mood="curious",
            ),
            reward_delta=0.2,
        )
    for _ in range(8):
        register_run_result(
            store,
            extract_run_features(
                operator="deadcode_elim",
                accepted=False,
                base_score=1.0,
                mutated_score=1.4,
                temperature=20.0,
                mood="curious",
            ),
            reward_delta=-0.4,
        )

    recommendation = recommend_strategy(
        store,
        failure_type="anticipated",
        environment_signal="stable",
        mood="curious",
        outcome_hint="success",
        candidates=["eq_rewrite_reduce_sum", "deadcode_elim"],
    )
    assert recommendation is not None
    assert recommendation.operator == "eq_rewrite_reduce_sum"
    assert recommendation.confidence > 0.7


def test_meta_learning_diverges_when_context_changes(tmp_path: Path) -> None:
    store = BeliefStore(path=tmp_path / "beliefs.json")
    for _ in range(6):
        register_run_result(
            store,
            extract_run_features(
                operator="const_tune",
                accepted=True,
                base_score=1.2,
                mutated_score=1.0,
                temperature=33.0,
                mood="fatigue",
            ),
            reward_delta=0.2,
        )
    for _ in range(6):
        register_run_result(
            store,
            extract_run_features(
                operator="eq_rewrite_reduce_sum",
                accepted=True,
                base_score=1.2,
                mutated_score=0.9,
                temperature=10.0,
                mood="neutre",
            ),
            reward_delta=0.3,
        )

    hot = recommend_strategy(
        store,
        failure_type="anticipated",
        environment_signal="hot",
        mood="fatigue",
        outcome_hint="success",
        candidates=["const_tune", "eq_rewrite_reduce_sum"],
    )
    stable = recommend_strategy(
        store,
        failure_type="anticipated",
        environment_signal="stable",
        mood="neutre",
        outcome_hint="success",
        candidates=["const_tune", "eq_rewrite_reduce_sum"],
    )

    assert hot is not None and stable is not None
    assert hot.operator == "const_tune"
    assert stable.operator == "eq_rewrite_reduce_sum"


def test_forgetting_progressively_removes_stale_rules(tmp_path: Path) -> None:
    store = BeliefStore(path=tmp_path / "beliefs.json", decay_per_day=1.2, ttl_days=1)
    anchor = datetime(2026, 4, 1, tzinfo=timezone.utc)
    store.update_probabilistic_rule(
        context_key="failure=rejected|env=stable|mood=neutre|outcome=failure",
        strategy="deadcode_elim",
        success=False,
        evidence="old",
        reward_delta=-0.2,
        when=anchor,
    )

    removed = store.forget_stale(when=anchor + timedelta(days=4))
    assert removed == 1


def test_meta_learning_documents_features_and_strategy_conditions(
    tmp_path: Path,
) -> None:
    store = BeliefStore(path=tmp_path / "beliefs.json")
    features = extract_run_features(
        operator="const_tune",
        accepted=True,
        base_score=2.0,
        mutated_score=1.5,
        temperature=2.0,
        mood=" Curious ",
    )

    assert features.feature_summary()["environment_signal"] == "cold"
    assert features.feature_summary()["score_delta"] == "-0.500000"
    assert "include score delta as reward evidence" in features.learning_conditions

    register_run_result(store, features, reward_delta=0.5)
    recommendation = recommend_strategy(
        store,
        failure_type="anticipated",
        environment_signal="cold",
        mood="curious",
        outcome_hint="success",
        candidates=["const_tune"],
    )

    assert recommendation is not None
    assert recommendation.operator == "const_tune"
    assert recommendation.supporting_features["mood"] == "curious"
    assert "highest stored confidence" in recommendation.strategy_reason
    assert (
        "rank candidates by decayed Bayesian confidence"
        in recommendation.learning_conditions
    )
