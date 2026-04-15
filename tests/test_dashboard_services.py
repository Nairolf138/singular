from __future__ import annotations

from pathlib import Path

from singular.dashboard.services.lives_comparison import aggregate_lives
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
        set_life_status=lambda *_: None,
        registry_life_meta=lambda life_name, lives: (life_name, lives.get(life_name)),
    )

    assert unattached["records_count"] == 0
    assert "alpha" in comparison
    assert comparison["alpha"]["failure_rate"] == 0.5
    assert comparison["alpha"]["mutations"] == 2
    assert comparison["alpha"]["trend"] in {"plateau", "dégradation", "amélioration"}
