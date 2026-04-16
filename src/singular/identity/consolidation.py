"""Periodic identity-memory consolidation pipeline (short-term -> long-term)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .episodic_store import EpisodicStore
from .semantic_memory import SemanticMemoryStore
from .self_model import SelfModelStore


@dataclass(frozen=True)
class ConsolidationPolicy:
    """Retention/compaction policy that preserves identity invariants."""

    keep_last_episodes: int = 1_000
    keep_top_self_model_entries: int = 100


@dataclass(frozen=True)
class ConsolidationResult:
    """Result metadata for one consolidation cycle."""

    consolidated_at: str
    episodes_seen: int
    facts_count: int
    episodic_compaction: dict[str, Any]


class ConsolidationPipeline:
    """Orchestrates identity memory consolidation into durable structures."""

    def __init__(
        self,
        *,
        mem_dir: Path | str,
        policy: ConsolidationPolicy | None = None,
    ) -> None:
        root = Path(mem_dir)
        self.policy = policy or ConsolidationPolicy()
        self.episodic = EpisodicStore(root / "episodic.jsonl")
        self.semantic = SemanticMemoryStore(root / "semantic_memory.json")
        self.self_model = SelfModelStore(root / "self_model.json")

    def run(self) -> ConsolidationResult:
        episodes = self.episodic.read_all()
        facts = self.semantic.consolidate_from_episodes(episodes)
        self.self_model.apply_facts(facts)
        self.self_model.compact(self.policy.keep_top_self_model_entries)
        compaction = self.episodic.compact(
            keep_last=self.policy.keep_last_episodes,
            preserve_identity_events=True,
        )
        return ConsolidationResult(
            consolidated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            episodes_seen=len(episodes),
            facts_count=len(facts),
            episodic_compaction=compaction,
        )
