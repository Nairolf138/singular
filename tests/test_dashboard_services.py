from __future__ import annotations

from pathlib import Path

from singular.dashboard.services.lives_comparison import aggregate_lives
from singular.dashboard.services.code_evolution import aggregate_code_evolution
from singular.dashboard.services.trajectory import build_trajectory


def test_trajectory_service_builds_priority_changes_and_links(tmp_path: Path) -> None:
    quests = tmp_path / "quests_state.json"
    quests.write_text('{"active":[{"name":"obj-a"}],"completed":[{"name":"obj-b"}]}' , encoding="utf-8")
    records = [
        {"ts": "2026-01-01T00:00:00Z", "objective_priorities": {"obj-a": 0.2}},
        {
            "ts": "2026-01-01T01:00:00Z",
            "objective_priorities": {"obj-a": 0.5},
            "event": "interaction",
            "objective": "obj-a",
            "run_id": "r-1",
        },
    ]

    payload = build_trajectory(records, quests, lambda rec: str(rec.get("run_id", "unknown")))

    assert payload["objectives"]["counts"]["in_progress"] == 1
    assert payload["objectives"]["counts"]["completed"] == 1
    assert payload["priority_changes"][0]["delta"] == 0.3
    assert payload["objective_narrative_links"][0]["run"] == "r-1"


def test_lives_comparison_service_aggregates_metrics() -> None:
    records = [
        {
            "life": "alpha",
            "ts": "2026-01-01T00:00:00Z",
            "score_base": 10,
            "score_new": 9,
            "accepted": True,
            "ms_new": 50,
            "health": {"score": 70.0, "sandbox_stability": 0.8},
        },
        {
            "life": "alpha",
            "ts": "2026-01-01T01:00:00Z",
            "score_base": 9,
            "score_new": 11,
            "accepted": False,
            "ms_new": 70,
            "health": {"score": 68.0, "sandbox_stability": 0.5},
        },
    ]

    comparison, unattached = aggregate_lives(
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
        registry_life_meta=lambda life_name, lives: (life_name, lives.get(life_name)),
    )

    assert unattached["records_count"] == 0
    assert "alpha" in comparison
    assert comparison["alpha"]["failure_rate"] == 0.5
    assert comparison["alpha"]["mutations"] == 2
    assert comparison["alpha"]["trend"] in {"plateau", "dégradation", "amélioration"}


def test_lives_comparison_includes_registry_life_without_records_in_table() -> None:
    comparison, _ = aggregate_lives(
        [
            {
                "life": "alpha",
                "ts": "2026-01-01T00:00:00Z",
                "score_base": 10,
                "score_new": 9,
            }
        ],
        registry={
            "active": "alpha",
            "lives": {
                "alpha": {"name": "alpha", "status": "active"},
                "beta": {"name": "beta", "status": "active"},
            },
        },
        compare_lives=None,
        time_window="all",
        record_life=lambda rec: str(rec.get("life", "unknown")),
        record_run_id=lambda rec: str(rec.get("run_id", "unknown")),
        is_mutation_record=lambda rec: "score_base" in rec,
        as_float=lambda value: float(value) if isinstance(value, (int, float)) else None,
        alerts_from_records=lambda _: [],
        compute_vital_timeline=lambda **_: {"ok": True},
        registry_life_meta=lambda life_name, lives: (life_name, lives.get(life_name)),
    )

    table = [{"life": name, **payload} for name, payload in comparison.items()]
    assert {row["life"] for row in table} == {"alpha", "beta"}
    beta = next(row for row in table if row["life"] == "beta")
    assert beta["current_health_score"] is None
    assert beta["iterations"] == 0
    assert beta["has_recent_activity"] is False


def test_lives_comparison_marks_selected_active_life_without_records() -> None:
    comparison, _ = aggregate_lives(
        [],
        registry={
            "active": "beta",
            "lives": {
                "alpha": {"name": "alpha", "status": "active"},
                "beta": {"name": "beta", "status": "active"},
            },
        },
        compare_lives=None,
        time_window="all",
        record_life=lambda rec: str(rec.get("life", "unknown")),
        record_run_id=lambda rec: str(rec.get("run_id", "unknown")),
        is_mutation_record=lambda rec: "score_base" in rec,
        as_float=lambda value: float(value) if isinstance(value, (int, float)) else None,
        alerts_from_records=lambda _: [],
        compute_vital_timeline=lambda **_: {"ok": True},
        registry_life_meta=lambda life_name, lives: (life_name, lives.get(life_name)),
    )

    assert comparison["beta"]["selected_life"] is True
    assert comparison["alpha"]["selected_life"] is False


def test_lives_comparison_default_rows_follow_active_and_dead_filters() -> None:
    comparison, _ = aggregate_lives(
        [],
        registry={
            "active": "alpha",
            "lives": {
                "alpha": {"name": "alpha", "status": "active"},
                "beta": {"name": "beta", "status": "extinct"},
            },
        },
        compare_lives=None,
        time_window="all",
        record_life=lambda rec: str(rec.get("life", "unknown")),
        record_run_id=lambda rec: str(rec.get("run_id", "unknown")),
        is_mutation_record=lambda rec: "score_base" in rec,
        as_float=lambda value: float(value) if isinstance(value, (int, float)) else None,
        alerts_from_records=lambda _: [],
        compute_vital_timeline=lambda **_: {"ok": True},
        registry_life_meta=lambda life_name, lives: (life_name, lives.get(life_name)),
    )

    table = [{"life": name, **payload} for name, payload in comparison.items()]
    active_only = [row for row in table if row.get("is_registry_active_life") is True]
    dead_only = [row for row in table if row.get("extinction_seen_in_runs") is True]

    assert [row["life"] for row in active_only] == ["alpha"]
    assert [row["life"] for row in dead_only] == ["beta"]


def test_code_evolution_service_aggregates_by_life_and_metrics() -> None:
    payload = aggregate_code_evolution(
        [
            {
                "life": "alpha",
                "file": "skills/a.py",
                "change_type": "perf_fix",
                "score_base": 10.0,
                "score_new": 8.0,
                "ms_base": 100.0,
                "ms_new": 75.0,
                "stability_base": 0.7,
                "stability_new": 0.9,
                "accepted": True,
                "ts": "2026-03-01T00:00:00Z",
                "run_id": "run-a",
                "trace_id": "trace-1",
            },
            {
                "life": "alpha",
                "module": "singular.life.loop",
                "operator": "cleanup",
                "score_base": 8.0,
                "score_new": 9.0,
                "ok": False,
                "ts": "2026-03-02T00:00:00Z",
                "run_id": "run-b",
                "trace_id": "trace-2",
            },
            {
                "life": "beta",
                "file": "skills/b.py",
                "change_type": "robustesse",
                "score_base": 9.0,
                "score_new": 7.0,
                "accepted": True,
                "ts": "2026-03-03T00:00:00Z",
                "run_id": "run-c",
            },
        ],
        life="alpha",
        record_life=lambda rec: str(rec.get("life", "unknown")),
        record_run_id=lambda rec: str(rec.get("run_id", "unknown")),
        as_float=lambda value: float(value) if isinstance(value, (int, float)) else None,
    )

    assert payload["life"] == "alpha"
    assert payload["count"] == 2
    assert payload["items"][0]["timestamp"] == "2026-03-02T00:00:00Z"
    assert payload["items"][1]["metrics"]["latency_ms"] == {"before": 100.0, "after": 75.0}
    assert payload["items"][1]["metrics"]["stability"] == {"before": 0.7, "after": 0.9}
    assert payload["summary"]["by_status"] == {"accepté": 1, "rejeté": 1}
    assert payload["summary"]["by_change_type"] == {"perf_fix": 1, "cleanup": 1}
    assert payload["summary"]["by_target"] == {"skills/a.py": 1, "singular.life.loop": 1}
