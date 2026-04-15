from __future__ import annotations

from pathlib import Path

from singular.dashboard.repositories.run_records import RunRecordsRepository


def test_run_records_repository_loads_jsonl_and_adds_run_file(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "alpha.jsonl").write_text('{"event":"mutation"}\nnot-json\n{"event":"death","_run_file":"custom"}\n', encoding="utf-8")

    repo = RunRecordsRepository(base_dir=tmp_path, runs_path=runs_dir, registry_loader=lambda: {})

    records = repo.load_run_records()

    assert len(records) == 2
    assert records[0]["_run_file"] == "alpha"
    assert records[1]["_run_file"] == "custom"


def test_run_records_repository_latest_file_uses_timestamp(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "a.jsonl").write_text('{"ts":"2026-01-01T00:00:00Z"}\n', encoding="utf-8")
    (runs_dir / "b.jsonl").write_text('{"ts":"2026-02-01T00:00:00Z"}\n', encoding="utf-8")

    repo = RunRecordsRepository(base_dir=tmp_path, runs_path=runs_dir, registry_loader=lambda: {})

    latest = repo.latest_run_file()

    assert latest is not None
    assert latest.stem == "b"
