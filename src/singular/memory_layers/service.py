from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from .base import MemoryBackend, MemoryRecord

_SHORT_TERM_LAYER = "short_term"
_LONG_TERM_LAYER = "long_term"
_SEMANTIC_LAYER = "semantic"
_PROCEDURAL_LAYER = "procedural"


class MemoryLayerService:
    """High-level memory orchestration with retention and consolidation."""

    def __init__(
        self,
        backend: MemoryBackend,
        *,
        short_term_window: int = 200,
        consolidate_every: int = 25,
    ) -> None:
        self.backend = backend
        self.short_term_window = max(1, short_term_window)
        self.consolidate_every = max(1, consolidate_every)
        self._episodes_since_consolidation = 0

    def ingest_episode(self, episode: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        record = MemoryRecord(
            id=_stable_id("episode", episode, now),
            text=_episode_text(episode),
            metadata={"kind": "episode", "ts": now, **episode},
        )
        self.backend.put(_SHORT_TERM_LAYER, record)
        self._episodes_since_consolidation += 1
        self._enforce_short_term_window()
        self._extract_semantic_facts(episode, now)
        if self._episodes_since_consolidation >= self.consolidate_every:
            self.consolidate()
            self._episodes_since_consolidation = 0

    def ingest_mutation_result(self, result: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        text = (
            f"Mutation skill={result.get('skill')} op={result.get('op')} "
            f"ok={result.get('ok')} score_new={result.get('score_new')}"
        )
        record = MemoryRecord(
            id=_stable_id("mutation", result, now),
            text=text,
            metadata={"kind": "mutation", "ts": now, **result},
        )
        self.backend.put(_PROCEDURAL_LAYER, record)

    def ingest_embodied_outcome(self, outcome: dict[str, Any]) -> None:
        """Store an executed/refused embodied outcome with its evidence anchor."""

        if outcome.get("dry_run"):
            return
        self.ingest_episode(outcome)

    def embodied_outcomes(
        self, *, objective: str = "", limit: int = 5
    ) -> list[dict[str, Any]]:
        """Retrieve outcomes by explicit causal provenance, not inferred similarity."""

        matches: list[dict[str, Any]] = []
        for layer in (_SHORT_TERM_LAYER, _LONG_TERM_LAYER):
            for record in self.backend.search(layer, query="", limit=10000):
                metadata = record.metadata
                if metadata.get("kind") != "episode" or not metadata.get("trace_id"):
                    continue
                if objective and str(metadata.get("objective")) != objective:
                    continue
                matches.append(
                    {
                        "provenance": f"causal:{metadata['trace_id']}",
                        "trace_id": metadata["trace_id"],
                        "objective": metadata.get("objective"),
                        "result": metadata.get("result"),
                        "confidence": metadata.get("confidence", 0.0),
                        "importance": metadata.get("importance", 0.0),
                        "summary": metadata.get("summary", record.text),
                    }
                )
        deduplicated = {row["trace_id"]: row for row in matches}
        return sorted(
            deduplicated.values(),
            key=lambda row: float(row.get("importance", 0.0)),
            reverse=True,
        )[: max(0, limit)]

    def consolidate(self) -> None:
        recent = self.backend.search(_SHORT_TERM_LAYER, query="", limit=10000)
        for rec in recent:
            long_rec = MemoryRecord(
                id=f"ltm-{rec.id}",
                text=rec.text,
                metadata={**rec.metadata, "consolidated": True},
            )
            self.backend.put(_LONG_TERM_LAYER, long_rec)

    def _enforce_short_term_window(self) -> None:
        records = self.backend.search(_SHORT_TERM_LAYER, query="", limit=100000)
        if len(records) <= self.short_term_window:
            return
        # backend.search sorts by score; for empty query scores are 0 => stable order by file order.
        overflow = len(records) - self.short_term_window
        for rec in records[:overflow]:
            self.backend.delete(_SHORT_TERM_LAYER, rec.id)

    def _extract_semantic_facts(self, episode: dict[str, Any], ts: str) -> None:
        for key in ("user_fact", "user_facts", "preference", "preferences"):
            value = episode.get(key)
            if value is None:
                continue
            if isinstance(value, list):
                values = [str(item) for item in value]
            else:
                values = [str(value)]
            for item in values:
                self.backend.put(
                    _SEMANTIC_LAYER,
                    MemoryRecord(
                        id=_stable_id("semantic", {"key": key, "value": item}, ts),
                        text=item,
                        metadata={"kind": "semantic", "category": key, "ts": ts},
                    ),
                )


def _episode_text(episode: dict[str, Any]) -> str:
    if "summary" in episode:
        return str(episode["summary"])
    if "event" in episode:
        return f"event={episode['event']} payload={json.dumps(episode, ensure_ascii=False)}"
    return json.dumps(episode, ensure_ascii=False)


def _stable_id(prefix: str, payload: dict[str, Any], ts: str) -> str:
    digest = hashlib.sha1(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:12]
    return f"{prefix}-{ts}-{digest}"
