import json
from pathlib import Path

from singular.memory_layers import (
    LocalJsonMemoryBackend,
    MemoryRecord,
    MemoryRetrievalService,
)
from singular.organisms.talk import ContextBudget, ContextItem, _build_structured_context


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_embedding_paraphrase_and_restart(tmp_path: Path) -> None:
    def embed(text: str) -> list[float]:
        return [1.0, 0.0] if "félin" in text or "chat" in text else [0.0, 1.0]

    layers = tmp_path / "mem" / "layers"
    backend = LocalJsonMemoryBackend(layers, embed=embed)
    backend.put(
        "long_term", MemoryRecord("pet", "Mon chat s'appelle Moka", {"confidence": 0.9})
    )

    # A freshly constructed service/backend proves persistence across restart.
    restarted = MemoryRetrievalService(
        tmp_path, LocalJsonMemoryBackend(layers, embed=embed)
    )
    result = restarted.retrieve("Quel est le nom de mon félin ?", limit=1)[0]
    assert result["id"] == "pet"
    assert (
        set(("source", "id", "date", "score", "confidence", "excerpt")) <= result.keys()
    )


def test_general_query_mixes_sources_and_respects_budget(tmp_path: Path) -> None:
    mem = tmp_path / "mem"
    mem.mkdir()
    (mem / "episodic.jsonl").write_text(
        json.dumps(
            {"id": "trip", "text": "souvenir important de voyage", "importance": 1.0}
        )
        + "\n",
        encoding="utf-8",
    )
    _write(
        mem / "semantic_memory.json",
        [{"id": "fact", "value": "souvenir de thé", "confidence": 0.8}],
    )
    _write(mem / "self_narrative.json", {"current_heading": "préserver mes souvenirs"})
    backend = LocalJsonMemoryBackend(mem / "layers")
    backend.put("long_term", MemoryRecord("long", "souvenir consolidé", {}))

    service = MemoryRetrievalService(tmp_path, backend)
    results = service.retrieve(
        "Quels souvenirs as-tu en général ?",
        active_objectives=["préserver mes souvenirs"],
        current_context={"topic": "souvenir"},
    )
    assert {item["source"] for item in results} >= {
        "episode",
        "semantic_fact",
        "self_narrative",
        "long_term",
    }
    selected = service.within_budget(results, 25)
    assert sum(len(item["excerpt"]) for item in selected) <= 25


def test_ranking_deduplication_and_life_isolation(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    _write(
        first / "mem" / "self_model.json",
        {"facts": [{"id": "a", "value": "Alice aime le thé", "importance": 1.0}]},
    )
    _write(first / "mem" / "self_narrative.json", {"duplicate": "Alice aime le thé"})
    _write(second / "mem" / "self_model.json", {"secret": "Bob aime le café"})
    service = MemoryRetrievalService(
        first, LocalJsonMemoryBackend(first / "mem" / "layers")
    )

    results = service.retrieve("Qui aime le thé ?")
    assert results[0]["id"] == "a"
    assert sum("Alice aime le thé" in item["excerpt"] for item in results) == 1
    assert all("Bob" not in item["excerpt"] for item in results)


def test_prompt_memory_selection_exposes_provenance_and_prefers_active_life() -> None:
    result = _build_structured_context(
        [
            ContextItem("recalled_memories", "Ada active", "episode:ada", relevance=.8, recency=.9, confidence=.9),
            ContextItem("recalled_memories", "Eve inactive", "episode:eve", relevance=.8, recency=.9, confidence=.9, active_life=False),
        ],
        ContextBudget(total=140, recalled_memories=70, safety=0),
    )
    assert "episode:ada" in result.text
    assert result.metrics["retained_ids"] == ["episode:ada"]
    assert result.metrics["dropped_ids"] == ["episode:eve"]
