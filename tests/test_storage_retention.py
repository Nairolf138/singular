from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from singular.storage_retention import (
    apply_runs_retention,
    build_runs_policy_report,
    load_retention_config,
    retention_status_snapshot,
    run_retention_service,
)


def test_load_retention_config_env_overrides_persisted(tmp_path, monkeypatch) -> None:
    persisted = tmp_path / "mem" / "retention_policy.json"
    persisted.parent.mkdir(parents=True)
    persisted.write_text(
        json.dumps(
            {
                "retention": {
                    "max_runs": 9,
                    "max_run_age_days": 88,
                    "max_total_runs_size_mb": 111,
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SINGULAR_RETENTION_MAX_RUNS", "3")

    config = load_retention_config(base_dir=tmp_path)

    assert config.max_runs == 3
    assert config.max_run_age_days == 88
    assert config.max_total_runs_size_mb == 111


def test_load_retention_config_uses_legacy_runs_keep_env(monkeypatch) -> None:
    monkeypatch.setenv("SINGULAR_RUNS_KEEP", "4")

    config = load_retention_config()

    assert config.max_runs == 4


def test_build_policy_report_marks_delete_and_keep(tmp_path) -> None:
    now = datetime(2026, 4, 15, tzinfo=timezone.utc)
    recent = tmp_path / "recent.jsonl"
    old = tmp_path / "old.jsonl"
    overflow = tmp_path / "overflow.jsonl"
    recent.write_text("{}\n", encoding="utf-8")
    old.write_text("{}\n", encoding="utf-8")
    overflow.write_text("x" * (2 * 1024 * 1024), encoding="utf-8")

    old_mtime = (now - timedelta(days=40)).timestamp()
    recent_mtime = (now - timedelta(days=1)).timestamp()
    overflow_mtime = (now - timedelta(days=2)).timestamp()
    recent.touch()
    old.touch()
    overflow.touch()
    # Deterministic ordering: recent, overflow, old
    import os

    os.utime(recent, (recent_mtime, recent_mtime))
    os.utime(overflow, (overflow_mtime, overflow_mtime))
    os.utime(old, (old_mtime, old_mtime))

    config = load_retention_config(
        environ={
            "SINGULAR_RETENTION_MAX_RUNS": "2",
            "SINGULAR_RETENTION_MAX_RUN_AGE_DAYS": "30",
            "SINGULAR_RETENTION_MAX_TOTAL_RUNS_SIZE_MB": "1",
        }
    )

    report = build_runs_policy_report(runs_dir=tmp_path, config=config, now=now)

    by_name = {p.target.split("/")[-1]: p for p in report.decisions}
    assert by_name["recent.jsonl"].action == "keep"
    assert by_name["old.jsonl"].action == "delete"
    assert by_name["overflow.jsonl"].action == "delete"
    assert by_name["overflow.jsonl"].reason == "max_total_runs_size_mb"


def test_apply_runs_retention_deletes_decisions(tmp_path) -> None:
    now = datetime(2026, 4, 15, tzinfo=timezone.utc)
    a = tmp_path / "a.jsonl"
    b = tmp_path / "b.jsonl"
    a.write_text("{}\n", encoding="utf-8")
    b.write_text("{}\n", encoding="utf-8")

    # Ensure one file is older so it gets deleted by max_runs=1
    import os

    os.utime(a, (now.timestamp(), now.timestamp()))
    older = (now - timedelta(days=1)).timestamp()
    os.utime(b, (older, older))

    config = load_retention_config(environ={"SINGULAR_RETENTION_MAX_RUNS": "1"})
    report = apply_runs_retention(runs_dir=tmp_path, config=config, now=now)

    assert (tmp_path / "a.jsonl").exists()
    assert not (tmp_path / "b.jsonl").exists()
    assert report.summary["delete"] == 1


def test_apply_runs_retention_deletes_run_directory_and_logs_decision(tmp_path) -> None:
    now = datetime(2026, 4, 15, tzinfo=timezone.utc)
    run_recent = tmp_path / "recent"
    run_old = tmp_path / "old"
    run_recent.mkdir()
    run_old.mkdir()
    (run_recent / "events.jsonl").write_text("{}\n", encoding="utf-8")
    (run_old / "events.jsonl").write_text("{}\n", encoding="utf-8")

    import os

    os.utime(run_recent / "events.jsonl", (now.timestamp(), now.timestamp()))
    older = (now - timedelta(days=1)).timestamp()
    os.utime(run_old / "events.jsonl", (older, older))

    config = load_retention_config(environ={"SINGULAR_RETENTION_MAX_RUNS": "1"})
    apply_runs_retention(runs_dir=tmp_path, config=config, now=now)

    assert run_recent.exists()
    assert not run_old.exists()
    retention_log = tmp_path.parent / "mem" / "retention.log.jsonl"
    lines = retention_log.read_text(encoding="utf-8").splitlines()
    assert any(json.loads(line).get("run_id") == "old" for line in lines)


def test_apply_runs_retention_protects_active_run(tmp_path) -> None:
    now = datetime(2026, 4, 15, tzinfo=timezone.utc)
    run_recent = tmp_path / "recent"
    run_old = tmp_path / "old"
    run_recent.mkdir()
    run_old.mkdir()
    (run_recent / "events.jsonl").write_text("{}\n", encoding="utf-8")
    (run_old / "events.jsonl").write_text("{}\n", encoding="utf-8")
    (run_old / ".active.lock").write_text("{}", encoding="utf-8")

    import os

    os.utime(run_recent / "events.jsonl", (now.timestamp(), now.timestamp()))
    older = (now - timedelta(days=1)).timestamp()
    os.utime(run_old / "events.jsonl", (older, older))

    config = load_retention_config(environ={"SINGULAR_RETENTION_MAX_RUNS": "1"})
    report = apply_runs_retention(runs_dir=tmp_path, config=config, now=now)

    assert run_recent.exists()
    assert run_old.exists()
    old_decision = next(d for d in report.decisions if d.run_id == "old")
    assert old_decision.reason == "active_run_protected"


def test_run_retention_service_dry_run_does_not_delete(tmp_path, monkeypatch) -> None:
    now = datetime(2026, 4, 15, tzinfo=timezone.utc)
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    recent = runs_dir / "recent.jsonl"
    old = runs_dir / "old.jsonl"
    recent.write_text("{}\n", encoding="utf-8")
    old.write_text("{}\n", encoding="utf-8")

    import os

    os.utime(recent, (now.timestamp(), now.timestamp()))
    older = (now - timedelta(days=1)).timestamp()
    os.utime(old, (older, older))
    monkeypatch.setenv("SINGULAR_RETENTION_MAX_RUNS", "1")

    outcome = run_retention_service(
        base_dir=tmp_path,
        runs_dir=runs_dir,
        dry_run=True,
        now=now,
        minimum_interval_minutes=30,
    )

    assert outcome.executed is True
    assert outcome.report is not None
    assert recent.exists()
    assert old.exists()
    assert any(
        decision.target.endswith("old.jsonl") and decision.action == "delete"
        for decision in outcome.report.decisions
    )
    assert not (tmp_path / "mem" / "retention_state.json").exists()


def test_run_retention_service_respects_minimum_interval(tmp_path) -> None:
    now = datetime(2026, 4, 15, tzinfo=timezone.utc)
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "a.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "mem").mkdir(parents=True, exist_ok=True)
    (tmp_path / "mem" / "retention_state.json").write_text(
        json.dumps({"last_full_run_at": (now - timedelta(minutes=5)).isoformat()}),
        encoding="utf-8",
    )

    outcome = run_retention_service(
        base_dir=tmp_path,
        runs_dir=runs_dir,
        now=now,
        minimum_interval_minutes=30,
    )

    assert outcome.executed is False
    assert outcome.report is None
    assert outcome.skipped_reason == "minimum_interval_not_elapsed"


def test_run_retention_service_persists_last_purge_summary(tmp_path, monkeypatch) -> None:
    now = datetime(2026, 4, 15, tzinfo=timezone.utc)
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    recent = runs_dir / "recent.jsonl"
    old = runs_dir / "old.jsonl"
    recent.write_text("{}\n", encoding="utf-8")
    old.write_text("{}\n", encoding="utf-8")

    import os

    os.utime(recent, (now.timestamp(), now.timestamp()))
    older = (now - timedelta(days=1)).timestamp()
    os.utime(old, (older, older))
    monkeypatch.setenv("SINGULAR_RETENTION_MAX_RUNS", "1")

    outcome = run_retention_service(base_dir=tmp_path, runs_dir=runs_dir, now=now)

    assert outcome.executed is True
    assert outcome.last_run_summary is not None
    assert outcome.last_run_summary["deleted"] == 1
    state = json.loads((tmp_path / "mem" / "retention_state.json").read_text(encoding="utf-8"))
    assert state["last_run_summary"]["deleted"] == 1


def test_retention_status_snapshot_reports_usage_and_thresholds(tmp_path, monkeypatch) -> None:
    runs_dir = tmp_path / "runs"
    mem_dir = tmp_path / "mem"
    lives_dir = tmp_path / "lives"
    runs_dir.mkdir()
    mem_dir.mkdir()
    lives_dir.mkdir()
    (runs_dir / "a.jsonl").write_text("{}\n", encoding="utf-8")
    (mem_dir / "events.jsonl").write_text("{}\n", encoding="utf-8")
    (lives_dir / "alpha.json").write_text("{}\n", encoding="utf-8")
    (mem_dir / "retention_state.json").write_text(
        json.dumps(
            {
                "last_full_run_at": "2026-04-15T10:00:00+00:00",
                "last_run_summary": {"freed_mb": 1.2, "deleted": 3, "archived": 0},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SINGULAR_RETENTION_MAX_RUNS", "1")
    monkeypatch.setenv("SINGULAR_RETENTION_MAX_TOTAL_RUNS_SIZE_MB", "1")

    payload = retention_status_snapshot(base_dir=tmp_path, now=datetime(2026, 4, 15, tzinfo=timezone.utc))

    assert payload["usage"]["runs"]["size_mb"] >= 0
    assert payload["usage"]["mem"]["size_mb"] >= 0
    assert payload["usage"]["lives"]["size_mb"] >= 0
    assert payload["thresholds"]["max_runs"] == 1
    assert payload["thresholds"]["max_total_runs_size_mb"] == 1
    assert payload["last_purge"]["summary"]["deleted"] == 3
