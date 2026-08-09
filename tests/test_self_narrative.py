from datetime import datetime, timedelta, timezone
from pathlib import Path

from singular.self_narrative import (
    SCHEMA_VERSION,
    diagnose_timeline,
    load,
    project_event,
    rebuild_from_timeline,
    summarize_long,
    summarize_short,
    update_from_signals,
)


def test_load_creates_default_file_when_missing(tmp_path: Path) -> None:
    path = tmp_path / "mem" / "self_narrative.json"

    narrative = load(path)

    assert path.exists()
    assert narrative.schema_version == SCHEMA_VERSION
    assert narrative.identity.name == "Singular"
    assert set(narrative.trait_trends) == {
        "curiosity",
        "patience",
        "playfulness",
        "optimism",
        "resilience",
    }


def test_contaminated_timeline_rebuilds_ada_bob_and_eve_separately(
    tmp_path: Path,
) -> None:
    path = tmp_path / "shared.json"
    for life, claim in (("Ada", "succès"), ("Bob", "échec"), ("Eve", "incident")):
        own = tmp_path / f"{life}.json"
        project_event(
            {"event_type": "incident", "event_id": life, "summary": claim},
            own,
            life_id=life,
        )
        with path.with_name("shared.timeline.jsonl").open(
            "a", encoding="utf-8"
        ) as target:
            target.write(
                own.with_name(f"{life}.timeline.jsonl").read_text(encoding="utf-8")
            )

    report = diagnose_timeline(path)
    assert report["contaminated"] is True
    assert set(report["lives"]) == {"ada", "bob", "eve"}
    rebuilt = {
        life: rebuild_from_timeline(path, life_id=life, persist=False)
        for life in report["lives"]
    }
    assert {entry.summary for entry in rebuilt["ada"].entries} == {"succès"}
    assert {entry.summary for entry in rebuilt["bob"].entries} == {"échec"}
    assert {entry.summary for entry in rebuilt["eve"].entries} == {"incident"}


def test_load_fallback_on_corrupted_file(tmp_path: Path) -> None:
    path = tmp_path / "mem" / "self_narrative.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-valid-json", encoding="utf-8")

    narrative = load(path)

    assert narrative.identity.name == "Singular"
    backups = list(path.parent.glob("self_narrative.json.corrupt-*"))
    assert backups


def test_update_from_signals_persists_expected_shape(tmp_path: Path) -> None:
    path = tmp_path / "mem" / "self_narrative.json"
    born_at = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()

    narrative = update_from_signals(
        {
            "identity": {"name": "Nova", "born_at": born_at},
            "current_heading": "Construire une mémoire plus robuste.",
            "life_periods": [
                {
                    "title": "Redémarrage",
                    "start_at": "2026-04-10T00:00:00+00:00",
                    "highlights": ["nettoyage", "recentrage"],
                }
            ],
            "trait_trends": {
                "curiosity": {"value": 0.8, "trend": "up"},
                "patience": {"value": 0.55, "trend": "stable"},
            },
            "regrets_and_pride": {
                "significant_successes": ["stabilité retrouvée"],
                "significant_failures": ["boucle trop coûteuse"],
                "abandoned_skills": ["heuristique-v0"],
                "costly_incidents": ["fuite mémoire"],
            },
        },
        path=path,
    )

    assert narrative.identity.name == "Nova"
    assert narrative.identity.logical_age >= 5
    assert narrative.life_periods[-1].title == "Redémarrage"
    assert narrative.trait_trends["curiosity"].trend == "up"
    assert "stabilité retrouvée" in narrative.regrets_and_pride.significant_successes


def test_summaries_include_current_heading(tmp_path: Path) -> None:
    path = tmp_path / "mem" / "self_narrative.json"
    update_from_signals({"current_heading": "Mieux décider."}, path)

    short = summarize_short(path=path)
    long = summarize_long(path=path)

    assert "cap" in short
    assert "Mieux décider." in short
    assert "Cap actuel" in long
    assert "Mieux décider." in long


def test_versioned_timeline_keeps_seven_injected_clock_days(tmp_path: Path) -> None:
    from singular.life.life_status import _extract_narrative_continuity_signal
    from singular.self_narrative import load_snapshots

    path = tmp_path / "mem" / "self_narrative.json"
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    for offset in range(7):
        instant = start + timedelta(days=offset)
        update_from_signals(
            {
                "identity": {"name": "Nova"},
                "current_heading": "Continuer",
                "event_count": 2,
            },
            path,
            clock=lambda instant=instant: instant,
        )

    snapshots = load_snapshots(path)
    signal = _extract_narrative_continuity_signal(
        {}, 7, snapshots=snapshots, now=start + timedelta(days=6, hours=1)
    )
    assert signal["ok"] is True
    assert signal["evidence"]["distinct_days"] == 7


def test_timeline_detects_missing_day_and_unexplained_identity_drift(
    tmp_path: Path,
) -> None:
    from singular.life.life_status import _extract_narrative_continuity_signal
    from singular.self_narrative import load_snapshots

    path = tmp_path / "mem" / "self_narrative.json"
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    for offset in (0, 1, 2, 4, 5, 6):
        update_from_signals(
            {"identity": {"name": "Nova"}, "current_heading": "Continuer"},
            path,
            clock=lambda offset=offset: start + timedelta(days=offset),
        )
    missing = _extract_narrative_continuity_signal(
        {}, 7, snapshots=load_snapshots(path), now=start + timedelta(days=6, hours=1)
    )
    assert missing["ok"] is False
    assert missing["evidence"]["distinct_days"] == 6

    update_from_signals(
        {"identity": {"name": "Autre"}, "current_heading": "Continuer"},
        path,
        clock=lambda: start + timedelta(days=7),
    )
    drift = _extract_narrative_continuity_signal(
        {}, 7, snapshots=load_snapshots(path), now=start + timedelta(days=7, hours=1)
    )
    assert drift["ok"] is False
    assert drift["evidence"]["unexplained_identity_ruptures"]


def test_trajectory_recovers_after_interruption_and_retention_preserves_it(
    tmp_path: Path,
) -> None:
    from singular.life.life_status import _extract_narrative_continuity_signal
    from singular.self_narrative import load_snapshots, timeline_path
    from singular.storage_retention import RetentionConfig, apply_runs_retention

    path = tmp_path / "mem" / "self_narrative.json"
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    for offset in (*range(3), *range(10, 17)):
        update_from_signals(
            {
                "identity": {"name": "Nova"},
                "current_heading": "Reprendre",
                "event_count": 1,
            },
            path,
            clock=lambda offset=offset: start + timedelta(days=offset),
        )
    signal = _extract_narrative_continuity_signal(
        {}, 7, snapshots=load_snapshots(path), now=start + timedelta(days=16, hours=1)
    )
    assert signal["ok"] is True

    before = timeline_path(path).read_bytes()
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "old.jsonl").write_text("{}\n", encoding="utf-8")
    apply_runs_retention(
        runs_dir=runs,
        config=RetentionConfig(max_runs=1, max_run_age_days=1),
        now=start + timedelta(days=30),
    )
    assert timeline_path(path).read_bytes() == before
