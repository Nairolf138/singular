import json
from datetime import UTC, datetime

import pytest

from singular.life.life_definition import LifeDefinitionConfig, LifeThresholds
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
        '{"source":"intrinsic","origin":"self_generated","kind":"intrinsic_goal","status":"active","weights":{"coherence":0.5},"history":[]}',
        encoding="utf-8",
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
            "children": ["alpha-child"],
        },
        runs=runs,
    )

    assert result.status == LifeStatus.ALIVE
    assert result.score == 100.0
    assert result.signals["persistent_identity"] is True
    assert result.signals["stable_cycle"] is True
    assert result.signals["intrinsic_goals"] is True
    assert result.signals["narrative_continuity"] is True


def test_compute_life_status_rejects_human_quest_as_intrinsic_goal(tmp_path) -> None:
    from singular.life.life_status import compute_life_status

    life_home = tmp_path
    mem = life_home / "mem"
    mem.mkdir()
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
        '{"weights":{"coherence":0.5},"history":[{"origin":"external","status":"active"}]}',
        encoding="utf-8",
    )
    (mem / "quests_state.json").write_text(
        '{"active":[{"origin":"external","status":"active"}],"paused":[]}',
        encoding="utf-8",
    )

    result = compute_life_status(
        life_home,
        registry_entry={
            "name": "Alpha",
            "slug": "alpha",
            "created_at": "2026-06-01T00:00:00+00:00",
            "status": "active",
        },
        runs=[],
    )

    assert result.signals["intrinsic_goals"] is False
    assert (
        result.signals["structured"]["goals"]["evidence"]["intrinsic_goal_weight_count"]
        == 0
    )


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


def test_compute_life_status_uses_vital_terminal_without_extinction(tmp_path) -> None:
    from singular.life.life_status import compute_life_status

    life_home = tmp_path / "lives" / "alpha"
    mem = life_home / "mem"
    mem.mkdir(parents=True)
    (mem / "world_state.json").write_text(
        '{"global_health":{"score":90}}', encoding="utf-8"
    )
    (mem / "autopsy.json").write_text("{}", encoding="utf-8")
    (mem / "self_narrative.json").write_text(
        '{"identity":{"name":"Alpha","born_at":"2026-06-01T00:00:00+00:00"},"current_heading":"continuer"}',
        encoding="utf-8",
    )
    (mem / "quests_state.json").write_text("{}", encoding="utf-8")
    runs = [
        {"event": "mutation", "score_new": index, "accepted": False}
        for index in range(5)
    ]

    result = compute_life_status(
        life_home,
        registry_entry={"name": "Alpha", "slug": "alpha", "status": "active"},
        runs=runs,
    )

    assert result.status == LifeStatus.DYING
    assert result.signals["terminal"] is True
    assert result.signals["extinction"] is False
    assert result.evidence["vital_timeline"]["state"] == "terminal"
    assert result.evidence["vital_timeline"]["risk_level"] == "high"
    assert "failure_streak" in result.evidence["vital_timeline"]["causes"]
    assert "failure_streak" in result.explanation


def test_compute_life_status_uses_vital_reproduction_eligibility(tmp_path) -> None:
    from singular.life.life_status import compute_life_status

    life_home = tmp_path / "lives" / "alpha"
    mem = life_home / "mem"
    mem.mkdir(parents=True)
    (mem / "world_state.json").write_text(
        '{"global_health":{"score":90}}', encoding="utf-8"
    )
    (mem / "autopsy.json").write_text("{}", encoding="utf-8")
    (mem / "self_narrative.json").write_text(
        '{"identity":{"name":"Alpha","born_at":"2026-06-01T00:00:00+00:00"},"current_heading":"continuer"}',
        encoding="utf-8",
    )
    (mem / "quests_state.json").write_text("{}", encoding="utf-8")
    runs = [
        {"event": "mutation", "score_new": index, "accepted": True}
        for index in range(3)
    ]

    result = compute_life_status(
        life_home,
        registry_entry={"name": "Alpha", "slug": "alpha", "status": "active"},
        runs=runs,
    )

    assert result.signals["reproduction_eligible"] is True
    assert result.signals["reproduction_capability"] is True
    assert result.evidence["vital_timeline"]["reproduction_eligible"] is True
    assert result.evidence["reproduction_capability"]["vital_age"] == 3
    assert result.evidence["reproduction_capability"]["vital_state"] == "mature"
    assert result.evidence["reproduction_capability"]["vital_thresholds"][
        "reproduction_age_window"
    ] == [3, 80]


def test_compute_life_status_detects_reproduction_events_and_descendants(
    tmp_path,
) -> None:
    from singular.life.life_status import compute_life_status

    life_home = tmp_path / "lives" / "alpha"
    mem = life_home / "mem"
    mem.mkdir(parents=True)
    (mem / "world_state.json").write_text(
        '{"global_health":{"score":90}}', encoding="utf-8"
    )
    (mem / "autopsy.json").write_text("{}", encoding="utf-8")
    (mem / "self_narrative.json").write_text(
        '{"identity":{"name":"Alpha","born_at":"2026-06-01T00:00:00+00:00"},"current_heading":"continuer"}',
        encoding="utf-8",
    )
    (mem / "quests_state.json").write_text("{}", encoding="utf-8")
    (mem / "generations.jsonl").write_text(
        json.dumps(
            {
                "event": "generation.accepted",
                "generation_id": 2,
                "parent_generation_id": 1,
                "clone_id": "alpha-clone-gen",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (mem / "lineage.json").write_text(
        json.dumps(
            {
                "alpha": {
                    "organism_id": "alpha",
                    "children": ["alpha-child-lineage"],
                    "generation": 0,
                }
            }
        ),
        encoding="utf-8",
    )

    result = compute_life_status(
        life_home,
        registry_entry={
            "name": "Alpha",
            "slug": "alpha",
            "status": "active",
            "children": ["alpha-child-registry"],
        },
        runs=[{"event": "clone.completed", "accepted": False}],
    )

    assert result.signals["reproduction_eligible"] is False
    assert result.signals["reproduction_capability"] is True
    assert result.signals["reproduction_done"] is True
    evidence = result.evidence["reproduction_capability"]
    assert evidence["reproduction_events_count"] == 1
    assert evidence["descendants"] == [
        "alpha-child-lineage",
        "alpha-child-registry",
        "alpha-clone-gen",
    ]


def test_private_life_status_helpers_return_structured_signals(tmp_path) -> None:
    from singular.life.life_status import (
        _extract_extinction_signal,
        _extract_generation_signal,
        _extract_goal_signal,
        _extract_identity_signal,
        _extract_narrative_continuity_signal,
        _read_json_object,
    )

    assert _read_json_object(tmp_path / "missing.json") == {}
    payload_path = tmp_path / "payload.json"
    payload_path.write_text('{"ok":true}', encoding="utf-8")
    assert _read_json_object(payload_path) == {"ok": True}

    narrative = {
        "identity": {"name": "Alpha", "born_at": "2026-06-01T00:00:00+00:00"},
        "current_heading": "continuer",
    }
    goals = {"weights": {"coherence": 0.8}}
    quests = {"active": [{"origin": "intrinsic"}], "paused": []}
    life_home = tmp_path / "life"
    mem = life_home / "mem"
    mem.mkdir(parents=True)
    (mem / "generations.jsonl").write_text(
        '{"event":"generation.accepted"}\n', encoding="utf-8"
    )
    runs = [{"event": "death confirmed"}]

    for signal in (
        _extract_identity_signal(narrative),
        _extract_narrative_continuity_signal(narrative, threshold_days=1),
        _extract_goal_signal(goals, quests, runs),
        _extract_generation_signal(life_home, runs),
        _extract_extinction_signal({}, "active", runs),
    ):
        assert set(signal) == {"ok", "score", "reason", "evidence"}
        assert signal["ok"] is True
        assert signal["score"] == 1.0
        assert isinstance(signal["reason"], str)
        assert isinstance(signal["evidence"], dict)


@pytest.fixture
def life_home_factory(tmp_path):
    """Build an isolated life_home with a mem/ directory for status tests."""

    def _build(name: str = "alpha"):
        life_home = tmp_path / "lives" / name
        mem = life_home / "mem"
        mem.mkdir(parents=True)
        return life_home, mem

    return _build


def _write_json(path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _cycle_runs(count: int) -> list[dict[str, str]]:
    return [
        {"event": phase, "ts": f"2026-06-{day:02d}T00:00:00+00:00"}
        for day in range(1, count + 1)
        for phase in ("veille", "action", "introspection", "sommeil")
    ]


def _assert_status_contract(result) -> None:
    assert 0 <= result.score <= 100
    assert result.explanation.strip()


def test_compute_life_status_no_artifacts_is_not_alive_yet(life_home_factory) -> None:
    from singular.life.life_status import LifeStatus, compute_life_status

    life_home, _mem = life_home_factory()

    result = compute_life_status(life_home, registry_entry={}, runs=[])

    assert result.status == LifeStatus.NOT_ALIVE_YET
    assert "world_state" in result.missing_signals
    assert "self_narrative" in result.missing_signals
    assert "registry_entry" in result.missing_signals
    _assert_status_contract(result)


def test_compute_life_status_identity_and_partial_cycle_is_fragile(
    life_home_factory,
) -> None:
    from singular.life.life_status import LifeStatus, compute_life_status

    life_home, mem = life_home_factory()
    _write_json(
        mem / "self_narrative.json", {"identity": {"name": "Alpha", "slug": "alpha"}}
    )
    _write_json(mem / "world_state.json", {"global_health": {"score": 85}})
    _write_json(mem / "quests_state.json", {})
    config = LifeDefinitionConfig(thresholds=LifeThresholds(fragile_minimum_score=0.2))

    result = compute_life_status(
        life_home,
        registry_entry={"name": "Alpha", "slug": "alpha", "status": "active"},
        runs=_cycle_runs(1),
        config=config,
    )

    assert result.status == LifeStatus.FRAGILE
    assert result.signals["persistent_identity"] is True
    assert result.signals["observed_cycles"] == 1
    assert result.signals["stable_cycle"] is False
    _assert_status_contract(result)


def test_compute_life_status_full_durable_signals_are_alive(life_home_factory) -> None:
    from singular.life.life_status import LifeStatus, compute_life_status

    life_home, mem = life_home_factory()
    _write_json(mem / "world_state.json", {"global_health": {"score": 95}})
    _write_json(
        mem / "self_narrative.json",
        {
            "identity": {"name": "Alpha", "born_at": "2026-06-01T00:00:00+00:00"},
            "current_heading": "continuer",
            "life_periods": [{"start_at": "2026-06-01T00:00:00+00:00"}],
        },
    )
    _write_json(
        mem / "goals.json",
        {
            "source": "intrinsic",
            "origin": "self_generated",
            "kind": "intrinsic_goal",
            "status": "active",
            "weights": {"coherence": 0.7},
            "history": [],
        },
    )
    _write_json(mem / "quests_state.json", {"active": [{"origin": "intrinsic"}]})
    (mem / "generations.jsonl").write_text(
        '{"event":"generation.accepted"}\n', encoding="utf-8"
    )

    result = compute_life_status(
        life_home,
        registry_entry={"name": "Alpha", "slug": "alpha", "status": "active"},
        runs=_cycle_runs(3),
    )

    assert result.status == LifeStatus.ALIVE
    assert result.signals["persistent_identity"] is True
    assert result.signals["generation_registry"] is True
    assert result.signals["stable_cycle"] is True
    assert result.signals["intrinsic_goals"] is True
    assert result.signals["narrative_continuity"] is True
    _assert_status_contract(result)


@pytest.mark.parametrize(
    ("world_state", "runs"),
    [
        ({"global_health": {"score": 0}}, []),
        (
            {"global_health": {"score": 90}},
            [
                {"event": "mutation", "score_new": index, "accepted": False}
                for index in range(5)
            ],
        ),
    ],
)
def test_compute_life_status_terminal_health_or_long_failures_are_dying(
    life_home_factory, world_state, runs
) -> None:
    from singular.life.life_status import LifeStatus, compute_life_status

    life_home, mem = life_home_factory()
    _write_json(mem / "world_state.json", world_state)
    _write_json(
        mem / "self_narrative.json", {"identity": {"name": "Alpha", "slug": "alpha"}}
    )
    _write_json(mem / "quests_state.json", {})

    result = compute_life_status(
        life_home,
        registry_entry={"name": "Alpha", "slug": "alpha", "status": "active"},
        runs=runs,
    )

    assert result.status == LifeStatus.DYING
    assert result.signals["terminal"] is True
    assert result.signals["extinction"] is False
    _assert_status_contract(result)


@pytest.mark.parametrize(
    ("autopsy", "registry_status", "runs"),
    [
        ({"technical_causes": ["mortality"]}, "active", []),
        ({}, "extinct", []),
        ({}, "active", [{"event": "death", "ts": "2026-06-05T00:00:00+00:00"}]),
    ],
)
def test_compute_life_status_extinction_evidence_is_extinct(
    life_home_factory, autopsy, registry_status, runs
) -> None:
    from singular.life.life_status import LifeStatus, compute_life_status

    life_home, mem = life_home_factory()
    _write_json(mem / "world_state.json", {"global_health": {"score": 90}})
    _write_json(mem / "autopsy.json", autopsy)
    _write_json(
        mem / "self_narrative.json", {"identity": {"name": "Alpha", "slug": "alpha"}}
    )
    _write_json(mem / "quests_state.json", {})

    result = compute_life_status(
        life_home,
        registry_entry={"name": "Alpha", "slug": "alpha", "status": registry_status},
        runs=runs,
    )

    assert result.status == LifeStatus.EXTINCT
    assert result.signals["extinction"] is True
    _assert_status_contract(result)


def test_compute_life_status_corrupt_json_and_missing_files_are_explanatory(
    life_home_factory,
) -> None:
    from singular.life.life_status import LifeStatus, compute_life_status

    life_home, mem = life_home_factory()
    (mem / "self_narrative.json").write_text("{not-json", encoding="utf-8")
    (mem / "quests_state.json").write_text("{not-json", encoding="utf-8")

    result = compute_life_status(
        life_home,
        registry_entry={"name": "Alpha", "slug": "alpha", "status": "active"},
        runs=[],
    )

    assert result.status == LifeStatus.NOT_ALIVE_YET
    assert (
        result.signals["structured"]["goals"]["reason"]
        == "no active self-generated intrinsic goal evidence found"
    )
    assert "world_state" in result.missing_signals
    assert "autopsy" in result.missing_signals
    assert "Manquants ou insuffisants" in result.explanation
    _assert_status_contract(result)


def test_compute_life_status_stable_cycle_records_last_cycles_and_tolerates_small_gap(
    life_home_factory,
) -> None:
    from singular.life.life_status import compute_life_status

    life_home, _mem = life_home_factory()
    runs = [
        {
            "event": "orchestrator.phase",
            "phase": "veille",
            "ts": "2026-06-02T00:00:00+00:00",
        },
        {
            "event": "orchestrator.phase",
            "phase": "action",
            "ts": "2026-06-02T00:01:00+00:00",
        },
        {
            "event": "orchestrator.phase",
            "phase": "introspection",
            "ts": "2026-06-02T00:02:00+00:00",
        },
        {
            "event": "orchestrator.phase",
            "phase": "sommeil",
            "ts": "2026-06-02T00:03:00+00:00",
        },
        {
            "event": "orchestrator.phase",
            "phase": "action",
            "ts": "2026-06-02T00:04:00+00:00",
        },
        {
            "event": "orchestrator.phase",
            "phase": "veille",
            "ts": "2026-06-02T00:05:00+00:00",
        },
        {
            "event": "orchestrator.phase",
            "phase": "action",
            "ts": "2026-06-02T00:06:00+00:00",
        },
        {
            "event": "orchestrator.phase",
            "phase": "introspection",
            "ts": "2026-06-02T00:07:00+00:00",
        },
        {
            "event": "orchestrator.phase",
            "phase": "sommeil",
            "ts": "2026-06-02T00:08:00+00:00",
        },
    ]
    config = LifeDefinitionConfig(
        thresholds=LifeThresholds(minimum_observed_cycles=2, maximum_cycle_anomalies=1)
    )

    result = compute_life_status(
        life_home, registry_entry={"status": "active"}, runs=runs, config=config
    )

    cycle = result.evidence["stable_cycle"]
    assert result.signals["stable_cycle"] is True
    assert result.signals["observed_cycles"] == 2
    assert cycle["anomalies"] == 1
    assert len(cycle["last_cycles"]) == 2
    assert [event["phase"] for event in cycle["last_cycles"][-1]] == [
        "veille",
        "action",
        "introspection",
        "sommeil",
    ]


def test_compute_life_status_stable_cycle_rejects_terminal_dominance(
    life_home_factory,
) -> None:
    from singular.life.life_status import compute_life_status

    life_home, _mem = life_home_factory()
    runs = _cycle_runs(3) + [
        {
            "event": "death.confirmed",
            "status": "terminal",
            "ts": "2026-06-03T00:00:00+00:00",
        }
        for _ in range(12)
    ]

    result = compute_life_status(
        life_home, registry_entry={"status": "active"}, runs=runs
    )

    cycle = result.evidence["stable_cycle"]
    assert result.signals["observed_cycles"] == 3
    assert result.signals["stable_cycle"] is False
    assert cycle["terminal_dominates"] is True
