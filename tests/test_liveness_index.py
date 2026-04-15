from __future__ import annotations

from datetime import datetime, timezone

from singular.dashboard.services.lives_comparison import aggregate_lives, compute_liveness_index


NOW = datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc)


def test_liveness_index_reaches_high_score_when_all_signals_present() -> None:
    records = [
        {"ts": "2026-04-15T10:00:00+00:00", "event": "perception", "perception_summary": "host stable"},
        {
            "ts": "2026-04-15T10:02:00+00:00",
            "event": "consciousness",
            "decision_reason": "best weighted score",
            "objective": "stabiliser",
            "status": "in_progress",
            "progress": 0.3,
        },
        {"ts": "2026-04-15T10:03:00+00:00", "event": "interaction", "interaction": {"with": "human"}},
        {
            "ts": "2026-04-15T10:05:00+00:00",
            "event": "mutation",
            "accepted": True,
            "score_base": 12.0,
            "score_new": 10.0,
            "health": {"score": 82.0},
        },
        {"ts": "2026-04-15T10:06:00+00:00", "event": "interaction", "speaker": "world"},
    ]

    payload = compute_liveness_index(records, now=NOW)

    assert payload["index"] == 100.0
    assert payload["components"]["recent_activity"]["score"] == 1.0
    assert payload["components"]["perception_decision_action_loop"]["completed"] is True
    assert payload["components"]["active_objectives_progress"]["score"] == 1.0
    assert payload["components"]["interactions"]["score"] == 1.0
    assert payload["components"]["validated_internal_modifications"]["score"] == 1.0
    assert len(payload["proofs"]) == 5


def test_liveness_index_avoids_false_positive_on_sparse_noise() -> None:
    records = [
        {"ts": "2026-04-10T10:00:00+00:00", "event": "heartbeat"},
        {"ts": "2026-04-15T11:00:00+00:00", "event": "heartbeat"},
        {"ts": "2026-04-15T11:10:00+00:00", "accepted": True},
    ]

    payload = compute_liveness_index(records, now=NOW)

    # Only one weak recent signal (accepted without validated usefulness).
    assert payload["index"] <= 20.0
    assert payload["components"]["active_objectives_progress"]["score"] == 0.0
    assert payload["components"]["interactions"]["score"] == 0.0
    assert payload["components"]["validated_internal_modifications"]["score"] == 0.0


def test_liveness_index_partial_interaction_threshold() -> None:
    records = [
        {"ts": "2026-04-15T10:00:00+00:00", "event": "interaction", "interaction": {"with": "human"}},
        {"ts": "2026-04-15T10:02:00+00:00", "event": "mutation", "accepted": False, "score_base": 5, "score_new": 7},
    ]

    payload = compute_liveness_index(records, now=NOW)

    assert payload["components"]["interactions"]["score"] == 0.5
    assert payload["components"]["interactions"]["count"] == 1


def test_lives_comparison_exposes_liveness_fields() -> None:
    records = [
        {
            "life": "alpha",
            "ts": "2026-04-15T10:00:00+00:00",
            "event": "perception",
            "score_base": 10.0,
            "score_new": 9.0,
            "accepted": True,
            "health": {"score": 75.0, "sandbox_stability": 0.8},
        },
        {
            "life": "alpha",
            "ts": "2026-04-15T10:01:00+00:00",
            "event": "consciousness",
            "decision_reason": "keep safe",
            "objective": "maintain",
            "status": "in_progress",
            "progress": 0.2,
        },
        {
            "life": "alpha",
            "ts": "2026-04-15T10:02:00+00:00",
            "event": "interaction",
            "interaction": {"with": "world"},
        },
    ]

    comparison, _ = aggregate_lives(
        records,
        registry={"active": "alpha", "lives": {"alpha": {"status": "active"}}},
        compare_lives=None,
        time_window="all",
        record_life=lambda rec: str(rec.get("life", "unknown")),
        record_run_id=lambda rec: str(rec.get("run_id", "unknown")),
        is_mutation_record=lambda rec: "score_base" in rec,
        as_float=lambda value: float(value) if isinstance(value, (int, float)) else None,
        alerts_from_records=lambda _: [],
        compute_vital_timeline=lambda **_: {"ok": True},
        set_life_status=lambda *_: None,
        registry_life_meta=lambda life_name, lives: (life_name, lives.get(life_name)),
    )

    alpha = comparison["alpha"]
    assert isinstance(alpha["life_liveness_index"], float)
    assert "recent_activity" in alpha["life_liveness_components"]
    assert isinstance(alpha["life_liveness_proofs"], list)
    assert len(alpha["life_liveness_proofs"]) <= 5
