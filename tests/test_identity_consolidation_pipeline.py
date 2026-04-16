from pathlib import Path

from singular.identity import ConsolidationPipeline, ConsolidationPolicy, EpisodicStore


def test_pipeline_consolidates_facts_and_updates_self_model(tmp_path: Path) -> None:
    mem = tmp_path / "mem"
    store = EpisodicStore(mem / "episodic.jsonl")
    store.append({"event": "identity.created", "summary": "boot"})
    store.append({"event": "conversation", "user_fact": "user_name:Alice"})
    store.append({"event": "conversation", "preference": "likes:tea"})
    store.append({"event": "conversation", "constraint": "prefers:privacy"})

    pipeline = ConsolidationPipeline(
        mem_dir=mem,
        policy=ConsolidationPolicy(keep_last_episodes=2, keep_top_self_model_entries=5),
    )
    result = pipeline.run()

    assert result.episodes_seen == 4
    assert result.facts_count == 3

    semantic_payload = (mem / "semantic_memory.json").read_text(encoding="utf-8")
    assert "likes:tea" in semantic_payload

    self_model_payload = (mem / "self_model.json").read_text(encoding="utf-8")
    assert "user_name:Alice" in self_model_payload
    assert "prefers:privacy" in self_model_payload


def test_pipeline_compaction_preserves_identity_invariants(tmp_path: Path) -> None:
    mem = tmp_path / "mem"
    store = EpisodicStore(mem / "episodic.jsonl")
    store.append({"event": "identity.created", "summary": "init"})
    for index in range(6):
        store.append({"event": "conversation", "summary": f"turn-{index}"})

    pipeline = ConsolidationPipeline(
        mem_dir=mem,
        policy=ConsolidationPolicy(keep_last_episodes=2, keep_top_self_model_entries=2),
    )
    pipeline.run()

    lines = (mem / "episodic.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert "identity.created" in lines[0]
