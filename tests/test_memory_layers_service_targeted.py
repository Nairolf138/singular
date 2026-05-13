from __future__ import annotations

import json

import pytest

from singular.memory_layers.base import MemoryRecord
from singular.memory_layers.local_json import LocalJsonMemoryBackend
from singular.memory_layers.service import MemoryLayerService


def _read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_memory_backend_put_is_atomic_and_recovers_after_replace_error(isolated_memory, monkeypatch) -> None:
    _service, backend, memory_dir = isolated_memory
    backend.put("short_term", MemoryRecord(id="existing", text="old"))
    before = (memory_dir / "short_term.jsonl").read_text(encoding="utf-8")

    def fail_replace(src, dst):
        raise OSError("simulated atomic replace failure")

    monkeypatch.setattr("singular.memory_layers.local_json.os.replace", fail_replace)

    with pytest.raises(OSError):
        backend.put("short_term", MemoryRecord(id="new", text="new"))

    assert (memory_dir / "short_term.jsonl").read_text(encoding="utf-8") == before
    assert not list(memory_dir.glob("*.tmp"))


def test_service_consolidates_short_term_into_long_term(isolated_memory) -> None:
    service, _backend, memory_dir = isolated_memory

    service.ingest_episode({"event": "first", "summary": "alpha"})
    service.ingest_episode({"event": "second", "summary": "beta"})

    long_term_rows = _read_jsonl(memory_dir / "long_term.jsonl")
    assert len(long_term_rows) == 2
    assert all(row["metadata"]["consolidated"] is True for row in long_term_rows)


def test_backend_skips_corrupt_jsonl_lines_and_keeps_valid_records(tmp_path) -> None:
    backend = LocalJsonMemoryBackend(tmp_path)
    (tmp_path / "short_term.jsonl").write_text(
        json.dumps({"id": "ok", "text": "alpha", "metadata": {}}) + "\n{bad json\n",
        encoding="utf-8",
    )

    records = backend.search("short_term", "alpha", limit=10)

    assert [record.id for record in records] == ["ok"]


def test_backend_deduplicates_records_by_id(isolated_memory) -> None:
    _service, backend, memory_dir = isolated_memory

    backend.put("semantic", MemoryRecord(id="same", text="old", metadata={"v": 1}))
    backend.put("semantic", MemoryRecord(id="same", text="new", metadata={"v": 2}))

    rows = _read_jsonl(memory_dir / "semantic.jsonl")
    assert len(rows) == 1
    assert rows[0]["text"] == "new"
    assert rows[0]["metadata"]["v"] == 2


def test_service_recovers_after_backend_error_on_next_ingest(tmp_path, monkeypatch) -> None:
    backend = LocalJsonMemoryBackend(tmp_path)
    service = MemoryLayerService(backend, short_term_window=5, consolidate_every=10)
    calls = {"count": 0}
    original_write = backend._write_layer

    def flaky_write(layer, records):
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("disk busy")
        return original_write(layer, records)

    monkeypatch.setattr(backend, "_write_layer", flaky_write)

    with pytest.raises(OSError):
        service.ingest_episode({"summary": "lost once"})
    service.ingest_episode({"summary": "recovered"})

    rows = _read_jsonl(tmp_path / "short_term.jsonl")
    assert len(rows) == 1
    assert rows[0]["text"] == "recovered"


def test_service_extracts_semantic_facts_and_enforces_short_term_window(isolated_memory) -> None:
    service, _backend, memory_dir = isolated_memory
    service.short_term_window = 2

    service.ingest_episode({"summary": "one", "preference": "tea"})
    service.ingest_episode({"summary": "two"})
    service.ingest_episode({"summary": "three"})

    short_term_rows = _read_jsonl(memory_dir / "short_term.jsonl")
    semantic_rows = _read_jsonl(memory_dir / "semantic.jsonl")

    assert [row["text"] for row in short_term_rows] == ["two", "three"]
    assert semantic_rows[0]["text"] == "tea"
