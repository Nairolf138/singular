"""Periodic identity-memory consolidation pipeline (short-term -> long-term)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .episodic_store import EpisodicStore
from .core import IdentityCoreService
from .semantic_memory import SemanticMemoryStore
from .self_model import SelfModelStore


@dataclass(frozen=True)
class ConsolidationPolicy:
    """Retention/compaction policy that preserves identity invariants."""

    keep_last_episodes: int = 1_000
    keep_top_self_model_entries: int = 100
    trait_minimum: float = 0.0
    trait_maximum: float = 1.0
    max_trait_delta: float = 0.10
    important_trait_delta: float = 0.15
    independent_evidence_required: int = 2
    structural_collapse_drop: float = 0.20


@dataclass(frozen=True)
class ConsolidationResult:
    """Result metadata for one consolidation cycle."""

    consolidated_at: str
    episodes_seen: int
    facts_count: int
    episodic_compaction: dict[str, Any]
    identity_evolution: dict[str, Any]


class ConsolidationPipeline:
    """Orchestrates identity memory consolidation into durable structures."""

    def __init__(
        self,
        *,
        mem_dir: Path | str,
        policy: ConsolidationPolicy | None = None,
    ) -> None:
        root = Path(mem_dir)
        self.mem_dir = root
        self.policy = policy or ConsolidationPolicy()
        self.episodic = EpisodicStore(root / "episodic.jsonl")
        self.semantic = SemanticMemoryStore(root / "semantic_memory.json")
        self.self_model = SelfModelStore(root / "self_model.json")

    def run(
        self, *, episodes: list[dict[str, Any]] | None = None
    ) -> ConsolidationResult:
        """Consolidate the supplied unprocessed episodes, then compact the journal.

        When ``episodes`` is omitted the complete journal is consolidated, preserving
        the public API used by standalone callers.  Orchestrators can pass only rows
        after their durable cursor to avoid inflating fact mention counts.
        """

        episodes = self.episodic.read_all() if episodes is None else episodes
        facts = self.semantic.consolidate_from_episodes(episodes)
        self.self_model.apply_facts(facts)
        evolution = self._apply_trait_evolution(episodes)
        self.self_model.compact(self.policy.keep_top_self_model_entries)
        # Reconcile projections after every consolidation so narrative, psyche,
        # birth artifacts and coherence do not drift into competing identities.
        IdentityCoreService(self.mem_dir).synchronize()
        compaction = self.episodic.compact(
            keep_last=self.policy.keep_last_episodes,
            preserve_identity_events=True,
        )
        return ConsolidationResult(
            consolidated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            episodes_seen=len(episodes),
            facts_count=len(facts),
            episodic_compaction=compaction,
            identity_evolution=evolution,
        )

    def _apply_trait_evolution(self, episodes: list[dict[str, Any]]) -> dict[str, Any]:
        """Apply evidence-bearing plastic changes separately from identity facts."""
        # Imported lazily because psyche persistence depends on the memory
        # package, whose layered services import the identity package.
        from singular.psyche import Psyche, TraitEvolutionPolicy

        path = self.mem_dir / "psyche.json"
        psyche = Psyche.load_state(path)
        psyche.evolution_policy = TraitEvolutionPolicy(
            minimum=self.policy.trait_minimum,
            maximum=self.policy.trait_maximum,
            max_delta=self.policy.max_trait_delta,
            important_delta=self.policy.important_trait_delta,
            independent_evidence_required=self.policy.independent_evidence_required,
            collapse_drop=self.policy.structural_collapse_drop,
        )
        counts = {"applied": 0, "review": 0, "frozen": 0}
        for episode in episodes:
            changes = episode.get("trait_changes")
            if not isinstance(changes, dict):
                continue
            evidence = episode.get("evidence", [])
            if isinstance(evidence, str):
                evidence = [evidence]
            status = psyche.evolve_traits(
                changes,
                cause=str(episode.get("cause") or episode.get("event") or "consolidation"),
                evidence=evidence if isinstance(evidence, list) else [],
            )
            counts[status] += 1
        if sum(counts.values()):
            psyche.save_state(path)
        return {**counts, "frozen_remaining": psyche.evolution_freeze_remaining}
