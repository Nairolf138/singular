from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path

from singular.memory_compaction import compact_episodic_jsonl
from singular.storage_retention import (
    apply_runs_retention,
    load_retention_config,
    run_retention_service,
)


def _write_blob(path: Path, *, size_kb: int, payload: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload * (size_kb * 1024), encoding="utf-8")


def _set_mtime(path: Path, dt: datetime) -> None:
    ts = dt.timestamp()
    os.utime(path, (ts, ts))


def _set_run_mtime(run_dir: Path, dt: datetime) -> None:
    _set_mtime(run_dir / "events.jsonl", dt)
    for child in run_dir.rglob("*"):
        _set_mtime(child, dt)
    _set_mtime(run_dir, dt)


def _tree_size_bytes(path: Path) -> int:
    return sum(file.stat().st_size for file in path.rglob("*") if file.is_file())


def _create_runs_fixture(root: Path, now: datetime) -> dict[str, Path]:
    runs = root / "runs"
    runs.mkdir(parents=True, exist_ok=True)

    recent = runs / "run-recent"
    old = runs / "run-old"
    ancient = runs / "run-ancient"
    active_old = runs / "run-active-old"

    _write_blob(recent / "events.jsonl", size_kb=8)
    _write_blob(recent / "snapshots" / "s1.json", size_kb=4)
    _set_run_mtime(recent, now - timedelta(days=1))

    _write_blob(old / "events.jsonl", size_kb=6)
    _set_run_mtime(old, now - timedelta(days=15))

    _write_blob(ancient / "events.jsonl", size_kb=6)
    _set_run_mtime(ancient, now - timedelta(days=45))

    _write_blob(active_old / "events.jsonl", size_kb=5)
    (active_old / ".active.lock").write_text("1", encoding="utf-8")
    _set_run_mtime(active_old, now - timedelta(days=60))

    mem = root / "mem"
    mem.mkdir(parents=True, exist_ok=True)
    episodic = mem / "episodic.jsonl"
    rows = [
        {
            "ts": (now - timedelta(minutes=400 - index)).isoformat(),
            "event": "observation",
            "text": f"entry-{index} " + ("signal " * 20),
        }
        for index in range(120)
    ]
    episodic.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    return {
        "runs": runs,
        "recent": recent,
        "old": old,
        "ancient": ancient,
        "active_old": active_old,
        "mem": mem,
        "episodic": episodic,
    }


def test_retention_purge_by_quantity(tmp_path: Path) -> None:
    now = datetime(2026, 4, 15, tzinfo=timezone.utc)
    fixture = _create_runs_fixture(tmp_path, now)

    config = load_retention_config(
        environ={
            "SINGULAR_RETENTION_MAX_RUNS": "2",
            "SINGULAR_RETENTION_MAX_RUN_AGE_DAYS": "365",
            "SINGULAR_RETENTION_MAX_TOTAL_RUNS_SIZE_MB": "512",
        }
    )
    report = apply_runs_retention(runs_dir=fixture["runs"], config=config, now=now)

    assert fixture["recent"].exists()
    assert fixture["old"].exists()
    assert not fixture["ancient"].exists()
    assert fixture["active_old"].exists()
    assert any(d.run_id == "run-ancient" and d.reason == "max_runs" for d in report.decisions)


def test_retention_purge_by_age(tmp_path: Path) -> None:
    now = datetime(2026, 4, 15, tzinfo=timezone.utc)
    fixture = _create_runs_fixture(tmp_path, now)

    config = load_retention_config(
        environ={
            "SINGULAR_RETENTION_MAX_RUNS": "20",
            "SINGULAR_RETENTION_MAX_RUN_AGE_DAYS": "30",
            "SINGULAR_RETENTION_MAX_TOTAL_RUNS_SIZE_MB": "512",
        }
    )
    report = apply_runs_retention(runs_dir=fixture["runs"], config=config, now=now)

    assert fixture["recent"].exists()
    assert fixture["old"].exists()
    assert not fixture["ancient"].exists()
    assert fixture["active_old"].exists()
    assert any(d.run_id == "run-ancient" and d.reason == "max_run_age_days" for d in report.decisions)


def test_retention_purge_by_size_budget(tmp_path: Path) -> None:
    now = datetime(2026, 4, 15, tzinfo=timezone.utc)
    runs = tmp_path / "runs"
    recent = runs / "budget-recent"
    old = runs / "budget-old"

    _write_blob(recent / "events.jsonl", size_kb=900)
    _write_blob(old / "events.jsonl", size_kb=700)
    _set_mtime(recent / "events.jsonl", now - timedelta(days=1))
    _set_mtime(old / "events.jsonl", now - timedelta(days=2))

    config = load_retention_config(
        environ={
            "SINGULAR_RETENTION_MAX_RUNS": "20",
            "SINGULAR_RETENTION_MAX_RUN_AGE_DAYS": "365",
            "SINGULAR_RETENTION_MAX_TOTAL_RUNS_SIZE_MB": "1",
        }
    )
    report = apply_runs_retention(runs_dir=runs, config=config, now=now)

    deleted = [d for d in report.decisions if d.action == "delete"]
    assert len(deleted) == 1
    assert deleted[0].reason == "max_total_runs_size_mb"
    assert (runs / deleted[0].run_id).exists() is False
    kept = [d.run_id for d in report.decisions if d.action == "keep"]
    assert len(kept) == 1


def test_retention_jsonl_compaction_reduces_episodic_size(tmp_path: Path) -> None:
    now = datetime(2026, 4, 15, tzinfo=timezone.utc)
    fixture = _create_runs_fixture(tmp_path, now)
    before_size = fixture["episodic"].stat().st_size

    result = compact_episodic_jsonl(
        mem_dir=fixture["mem"],
        keep_last_events=10,
        snapshot_chunk_size=25,
        max_examples_per_snapshot=3,
        now=now,
    )

    after_size = fixture["episodic"].stat().st_size
    assert result["compacted"] is True
    assert result["snapshot_count"] >= 1
    assert after_size < before_size
    snapshots = list((fixture["mem"] / "episodic_snapshots").glob("*.json"))
    assert snapshots


def test_retention_active_runs_are_protected(tmp_path: Path) -> None:
    now = datetime(2026, 4, 15, tzinfo=timezone.utc)
    fixture = _create_runs_fixture(tmp_path, now)

    config = load_retention_config(
        environ={
            "SINGULAR_RETENTION_MAX_RUNS": "1",
            "SINGULAR_RETENTION_MAX_RUN_AGE_DAYS": "1",
            "SINGULAR_RETENTION_MAX_TOTAL_RUNS_SIZE_MB": "1",
        }
    )
    report = apply_runs_retention(runs_dir=fixture["runs"], config=config, now=now)

    active_decision = next(d for d in report.decisions if d.run_id == "run-active-old")
    assert active_decision.reason == "active_run_protected"
    assert fixture["active_old"].exists()


def test_retention_is_idempotent_across_two_runs(tmp_path: Path, monkeypatch) -> None:
    now = datetime(2026, 4, 15, tzinfo=timezone.utc)
    fixture = _create_runs_fixture(tmp_path, now)
    monkeypatch.setenv("SINGULAR_RETENTION_MAX_RUNS", "2")
    monkeypatch.setenv("SINGULAR_RETENTION_MAX_RUN_AGE_DAYS", "365")
    monkeypatch.setenv("SINGULAR_RETENTION_MAX_TOTAL_RUNS_SIZE_MB", "512")

    first = run_retention_service(
        base_dir=tmp_path,
        runs_dir=fixture["runs"],
        now=now,
        enforce_minimum_interval=False,
    )
    after_first_size = _tree_size_bytes(fixture["runs"])

    second = run_retention_service(
        base_dir=tmp_path,
        runs_dir=fixture["runs"],
        now=now + timedelta(hours=1),
        enforce_minimum_interval=False,
    )
    after_second_size = _tree_size_bytes(fixture["runs"])

    assert first.executed is True
    assert second.executed is True
    assert after_second_size == after_first_size
    assert second.last_run_summary is not None
    assert second.last_run_summary["deleted"] == 0


def test_retention_dry_run_has_no_side_effects(tmp_path: Path, monkeypatch) -> None:
    now = datetime(2026, 4, 15, tzinfo=timezone.utc)
    fixture = _create_runs_fixture(tmp_path, now)
    before_listing = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*"))
    before_runs_size = _tree_size_bytes(fixture["runs"])

    monkeypatch.setenv("SINGULAR_RETENTION_MAX_RUNS", "1")
    outcome = run_retention_service(
        base_dir=tmp_path,
        runs_dir=fixture["runs"],
        dry_run=True,
        now=now,
        enforce_minimum_interval=False,
    )

    after_listing = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*"))
    after_runs_size = _tree_size_bytes(fixture["runs"])

    assert outcome.executed is True
    assert outcome.dry_run is True
    assert outcome.report is not None
    assert any(decision.action == "delete" for decision in outcome.report.decisions)
    assert before_listing == after_listing
    assert before_runs_size == after_runs_size
    assert not (tmp_path / "mem" / "retention_state.json").exists()
