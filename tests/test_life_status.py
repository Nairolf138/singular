from datetime import UTC, datetime

from singular.life.life_status import (
    AUTHORIZED_LIFE_STATUSES,
    LifeStatus,
    LifeStatusResult,
)


def test_authorized_life_statuses_are_stable_contract() -> None:
    assert AUTHORIZED_LIFE_STATUSES == (
        "not_alive_yet",
        "fragile",
        "alive",
        "dying",
        "extinct",
    )


def test_life_status_result_to_payload_serializes_portable_contract() -> None:
    computed_at = datetime(2026, 7, 7, 12, 30, tzinfo=UTC)
    result = LifeStatusResult(
        status=LifeStatus.ALIVE,
        score=0.91,
        explanation="Stable identity and cycle are observed.",
        signals={"stable_cycle": True, "observed_cycles": 4},
        missing_signals=("narrative_continuity",),
        evidence={"source": "test"},
        computed_at=computed_at,
    )

    assert result.to_payload() == {
        "status": "alive",
        "score": 0.91,
        "explanation": "Stable identity and cycle are observed.",
        "signals": {"stable_cycle": True, "observed_cycles": 4},
        "missing_signals": ["narrative_continuity"],
        "evidence": {"source": "test"},
        "computed_at": "2026-07-07T12:30:00+00:00",
    }


def test_compute_life_status_aggregates_configured_signals(tmp_path) -> None:
    from singular.life.life_status import compute_life_status

    life_home = tmp_path / "lives" / "alpha"
    mem = life_home / "mem"
    mem.mkdir(parents=True)
    (life_home / "runs").mkdir()
    (mem / "world_state.json").write_text(
        '{"global_health":{"score":90}}', encoding="utf-8"
    )
    (mem / "autopsy.json").write_text("{}", encoding="utf-8")
    (mem / "self_narrative.json").write_text(
        '{"identity":{"name":"Alpha","born_at":"2026-06-01T00:00:00+00:00"},"current_heading":"continuer","life_periods":[]}',
        encoding="utf-8",
    )
    (mem / "goals.json").write_text(
        '{"weights":{"coherence":0.5},"history":[]}', encoding="utf-8"
    )
    (mem / "quests_state.json").write_text(
        '{"active":[{"origin":"intrinsic"}],"paused":[]}', encoding="utf-8"
    )
    (mem / "generations.jsonl").write_text(
        '{"event":"generation.accepted"}\n', encoding="utf-8"
    )
    runs = [
        {"event": phase, "ts": "2026-06-02T00:00:00+00:00"}
        for _ in range(3)
        for phase in ("veille", "action", "introspection", "sommeil")
    ]

    result = compute_life_status(
        life_home,
        registry_entry={
            "name": "Alpha",
            "slug": "alpha",
            "created_at": "2026-06-01T00:00:00+00:00",
            "status": "active",
        },
        runs=runs,
    )

    assert result.status == LifeStatus.ALIVE
    assert result.score == 100.0
    assert result.signals["persistent_identity"] is True
    assert result.signals["stable_cycle"] is True
    assert result.signals["intrinsic_goals"] is True
    assert result.signals["narrative_continuity"] is True


def test_compute_life_status_terminal_signal_dominates(tmp_path) -> None:
    from singular.life.life_status import compute_life_status

    life_home = tmp_path / "lives" / "alpha"
    mem = life_home / "mem"
    mem.mkdir(parents=True)
    (mem / "world_state.json").write_text("{}", encoding="utf-8")
    (mem / "autopsy.json").write_text(
        '{"technical_causes":["mortality"]}', encoding="utf-8"
    )
    (mem / "self_narrative.json").write_text(
        '{"identity":{"name":"Alpha"}}', encoding="utf-8"
    )
    (mem / "quests_state.json").write_text("{}", encoding="utf-8")

    result = compute_life_status(
        life_home,
        registry_entry={"name": "Alpha", "slug": "alpha", "status": "active"},
        runs=[],
    )

    assert result.status == LifeStatus.EXTINCT
    assert result.signals["terminal"] is True
