from pathlib import Path
import json
import sqlite3

from singular.storage import (
    EpisodesRepository,
    RunsRepository,
    SQLiteStorage,
    StorageConfig,
    WorldStateRepository,
    SkillScoresRepository,
    import_legacy_storage,
)


def test_sqlite_storage_enables_wal_and_repositories_roundtrip(tmp_path: Path) -> None:
    storage = SQLiteStorage(StorageConfig(root=tmp_path))
    with storage.connect() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"

    EpisodesRepository(storage).add(
        {"ts": "2026-01-01T00:00:00", "event": "memory", "text": "hello"}
    )
    WorldStateRepository(storage).save_snapshot(
        {"ts": "2026-01-02T00:00:00", "weather": "clear"}
    )
    RunsRepository(storage).add_event(
        "run-a", {"ts": "2026-01-03T00:00:00", "event": "mutation", "skill": "x"}
    )
    SkillScoresRepository(storage).upsert(
        "x",
        {"success_rate": 1.0, "mean_cost": 0.5, "use_count": 3},
        quarantined=True,
        quarantine_reason="test",
    )

    assert EpisodesRepository(storage).list()[0]["text"] == "hello"
    assert WorldStateRepository(storage).latest()["weather"] == "clear"
    assert RunsRepository(storage).list_events("run-a")[0]["_run_file"] == "run-a"
    assert SkillScoresRepository(storage).get("x")["quarantined"] is True


def test_import_legacy_storage_keeps_json_files_and_imports_tables(
    tmp_path: Path,
) -> None:
    mem = tmp_path / "mem"
    runs = tmp_path / "runs"
    mem.mkdir()
    runs.mkdir()
    (mem / "episodic.jsonl").write_text(
        '{"event":"episode","ts":"t1"}\n', encoding="utf-8"
    )
    (mem / "world_state.json").write_text(
        json.dumps({"ts": "t2", "status": "ok"}), encoding="utf-8"
    )
    (runs / "alpha-20260101000000.jsonl").write_text(
        '{"event":"mutation","ts":"t3","skill":"s"}\n', encoding="utf-8"
    )

    counts = import_legacy_storage(tmp_path)

    assert counts == {"episodes": 1, "world_state_snapshots": 1, "run_events": 1}
    assert (mem / "episodic.jsonl").exists()
    assert (mem / "world_state.json").exists()
    with sqlite3.connect(tmp_path / "mem" / "singular.sqlite3") as conn:
        assert conn.execute("SELECT count(*) FROM episodes").fetchone()[0] == 1
        assert conn.execute("SELECT run_id FROM run_events").fetchone()[0] == "alpha"
