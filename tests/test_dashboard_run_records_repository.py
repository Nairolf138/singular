from __future__ import annotations

from pathlib import Path
import json

from singular.dashboard.repositories.run_records import RunRecordsRepository


def test_run_records_repository_loads_jsonl_and_adds_run_file(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "alpha.jsonl").write_text(
        '{"event":"mutation"}\nnot-json\n{"event":"death","_run_file":"custom"}\n',
        encoding="utf-8",
    )

    repo = RunRecordsRepository(
        base_dir=tmp_path, runs_path=runs_dir, registry_loader=lambda: {}
    )

    records = repo.load_run_records()

    assert len(records) == 2
    assert records[0]["_run_file"] == "alpha"
    assert records[1]["_run_file"] == "custom"


def test_run_records_repository_latest_file_uses_timestamp(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "a.jsonl").write_text(
        '{"ts":"2026-01-01T00:00:00Z"}\n', encoding="utf-8"
    )
    (runs_dir / "b.jsonl").write_text(
        '{"ts":"2026-02-01T00:00:00Z"}\n', encoding="utf-8"
    )

    repo = RunRecordsRepository(
        base_dir=tmp_path, runs_path=runs_dir, registry_loader=lambda: {}
    )

    latest = repo.latest_run_file()

    assert latest is not None
    assert latest.stem == "b"


def test_run_records_repository_runs_dirs_supports_dict_registry_metadata(
    tmp_path: Path,
) -> None:
    alpha_dir = tmp_path / "alpha"
    repo = RunRecordsRepository(
        base_dir=tmp_path,
        runs_path=None,
        registry_loader=lambda: {"lives": {"alpha": {"path": str(alpha_dir)}}},
    )

    runs_dirs = repo.runs_dirs()

    assert alpha_dir / "runs" in runs_dirs


def test_jsonl_iterator_bounds_large_logs_and_skips_oversized_events(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    log = runs_dir / "large.jsonl"
    with log.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps({"event": "oversized", "data": "x" * 20_000}) + "\n")
        for index in range(5_000):
            handle.write(json.dumps({"event": "small", "index": index}) + "\n")

    repo = RunRecordsRepository(
        base_dir=tmp_path, runs_path=runs_dir, registry_loader=lambda: {}
    )
    records = list(
        repo.iter_jsonl_records(
            log, max_lines=101, max_bytes=32_000, max_event_bytes=1_024
        )
    )

    assert len(records) <= 100
    assert records
    assert all(record["event"] == "small" for record in records)


def test_jsonl_iterator_skips_invalid_utf8_without_losing_following_event(
    tmp_path: Path,
) -> None:
    log = tmp_path / "decode.jsonl"
    log.write_bytes(b'{"event":"bad","value":"\xff"}\n{"event":"good"}\n')
    repo = RunRecordsRepository(
        base_dir=tmp_path, runs_path=tmp_path, registry_loader=lambda: {}
    )

    assert list(repo.iter_jsonl_records(log)) == [{"event": "good"}]
