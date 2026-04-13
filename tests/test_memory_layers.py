from __future__ import annotations

import json

from singular.memory_layers import LocalJsonMemoryBackend, MemoryLayerService


def test_local_backend_put_search_delete(tmp_path):
    backend = LocalJsonMemoryBackend(tmp_path / "layers")
    from singular.memory_layers.base import MemoryRecord

    backend.put("short_term", MemoryRecord(id="1", text="likes python", metadata={}))
    backend.put("short_term", MemoryRecord(id="2", text="likes rust", metadata={}))

    res = backend.search("short_term", "python", limit=1)
    assert len(res) == 1
    assert res[0].id == "1"

    assert backend.delete("short_term", "1") is True
    assert backend.delete("short_term", "404") is False


def test_service_retention_and_consolidation(tmp_path):
    backend = LocalJsonMemoryBackend(tmp_path / "layers")
    service = MemoryLayerService(backend, short_term_window=2, consolidate_every=2)

    service.ingest_episode({"event": "a", "summary": "alpha"})
    service.ingest_episode({"event": "b", "summary": "beta"})
    service.ingest_episode({"event": "c", "summary": "gamma"})

    short_path = tmp_path / "layers" / "short_term.jsonl"
    long_path = tmp_path / "layers" / "long_term.jsonl"

    short_lines = [line for line in short_path.read_text(encoding="utf-8").splitlines() if line]
    assert len(short_lines) == 2

    long_lines = [line for line in long_path.read_text(encoding="utf-8").splitlines() if line]
    assert len(long_lines) >= 2


def test_add_episode_enriches_semantic_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))

    from singular.memory import add_episode, get_memory_layers_dir

    add_episode(
        {
            "event": "user_profile",
            "user_facts": ["lives in paris"],
            "preferences": ["coffee"],
        }
    )

    semantic_path = get_memory_layers_dir() / "semantic.jsonl"
    lines = [json.loads(line) for line in semantic_path.read_text(encoding="utf-8").splitlines()]
    texts = [entry["text"] for entry in lines]
    assert "lives in paris" in texts
    assert "coffee" in texts
