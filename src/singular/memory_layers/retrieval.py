"""Life-scoped retrieval across autobiographical memory sources."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .base import MemoryBackend


@dataclass(frozen=True)
class RetrievalResult:
    source: str
    id: str
    date: str | None
    score: float
    confidence: float
    excerpt: str

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value.update({"ts": self.date, "summary": self.excerpt})
        return value


class MemoryRetrievalService:
    """Rank persisted memories belonging exclusively to one life directory."""

    def __init__(self, life_root: Path | str, backend: MemoryBackend) -> None:
        self.life_root = Path(life_root).resolve()
        self.mem = self.life_root / "mem"
        self.backend = backend

    def retrieve(
        self,
        user_query: str,
        *,
        active_objectives: Iterable[str] = (),
        current_context: Mapping[str, Any] | str | None = None,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        context = (
            json.dumps(current_context, ensure_ascii=False, sort_keys=True)
            if isinstance(current_context, Mapping)
            else str(current_context or "")
        )
        query = " ".join(
            part for part in (user_query, " ".join(active_objectives), context) if part
        )
        now = datetime.now(timezone.utc)
        ranked: list[tuple[float, dict[str, Any]]] = []
        for item in self._file_candidates() + self._layer_candidates(query):
            relevance = max(0.0, float(self.backend.similarity(query, item["excerpt"])))
            # Importance and recency rerank matches; they cannot create one.
            if relevance <= 0.0:
                continue
            confidence = max(0.0, min(1.0, float(item.get("confidence", 0.7))))
            score = (
                0.62 * relevance
                + 0.14 * _recency(item.get("date"), now)
                + 0.14 * float(item.get("importance", 0.5))
                + 0.10 * confidence
            )
            ranked.append((score, item))

        seen: set[str] = set()
        results: list[RetrievalResult] = []
        source_counts: dict[str, int] = {}
        for score, item in sorted(ranked, key=lambda pair: pair[0], reverse=True):
            fingerprint = _fingerprint(item["excerpt"])
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            source = item["source"]
            score *= 0.82 ** source_counts.get(source, 0)
            results.append(
                RetrievalResult(
                    source,
                    item["id"],
                    item.get("date"),
                    round(score, 6),
                    round(float(item.get("confidence", 0.7)), 4),
                    item["excerpt"][:360],
                )
            )
            source_counts[source] = source_counts.get(source, 0) + 1
        results.sort(key=lambda result: result.score, reverse=True)
        return [result.as_dict() for result in results[: max(0, limit)]]

    @staticmethod
    def within_budget(
        results: Iterable[Mapping[str, Any]], budget_chars: int
    ) -> list[dict[str, Any]]:
        """Select complete ranked excerpts without exceeding the context budget."""
        selected, used = [], 0
        for result in results:
            cost = len(str(result.get("excerpt") or result.get("summary") or ""))
            if used + cost <= max(0, budget_chars):
                selected.append(dict(result))
                used += cost
        return selected

    def _file_candidates(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for index, payload in enumerate(_read_jsonl(self.mem / "episodic.jsonl")):
            if str(payload.get("event", "")).startswith("memory."):
                continue
            text = _best_text(payload)
            if text:
                rows.append(_candidate("episode", payload, text, str(index)))
        for filename, source in (
            ("semantic_memory.json", "semantic_fact"),
            ("self_model.json", "self_model"),
            ("self_narrative.json", "self_narrative"),
        ):
            for index, (trail, value, metadata) in enumerate(
                _leaves(_read_json(self.mem / filename))
            ):
                # Structured fact objects already carry their own provenance;
                # avoid diluting their semantic text with JSON field paths.
                excerpt = (
                    value if metadata else (f"{trail}: {value}" if trail else value)
                )
                rows.append(
                    _candidate(
                        source,
                        metadata,
                        excerpt,
                        str(index),
                    )
                )
        return rows

    def _layer_candidates(self, query: str) -> list[dict[str, Any]]:
        rows = []
        for layer, source in (
            ("semantic", "semantic_fact"),
            ("long_term", "long_term"),
        ):
            for record in self.backend.search(layer, query, limit=50):
                metadata = record.metadata
                rows.append(
                    {
                        "source": source,
                        "id": record.id,
                        "date": metadata.get("ts") or metadata.get("date"),
                        "confidence": metadata.get("confidence", 0.75),
                        "importance": metadata.get(
                            "importance", 0.65 if source == "long_term" else 0.55
                        ),
                        "excerpt": record.text,
                    }
                )
        return rows


def _candidate(
    source: str, metadata: Mapping[str, Any], text: str, fallback: str
) -> dict[str, Any]:
    return {
        "source": source,
        "id": str(
            metadata.get("id") or metadata.get("episode_id") or f"{source}-{fallback}"
        ),
        "date": metadata.get("ts")
        or metadata.get("date")
        or metadata.get("updated_at"),
        "confidence": metadata.get(
            "confidence", 0.8 if source.startswith("self_") else 0.7
        ),
        "importance": metadata.get(
            "importance", 0.85 if source in {"self_model", "self_narrative"} else 0.5
        ),
        "excerpt": " ".join(text.split()),
    }


def _best_text(payload: Mapping[str, Any]) -> str:
    return next(
        (
            payload[key]
            for key in ("text", "summary", "message", "human_summary", "event")
            if isinstance(payload.get(key), str) and payload[key].strip()
        ),
        "",
    )


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [
            value
            for line in path.read_text(encoding="utf-8").splitlines()
            if isinstance((value := json.loads(line)), dict)
        ]
    except (OSError, json.JSONDecodeError):
        return []


def _leaves(
    value: Any, trail: str = ""
) -> Iterable[tuple[str, str, Mapping[str, Any]]]:
    if isinstance(value, dict):
        if isinstance(value.get("value"), (str, int, float, bool)):
            yield trail, str(value["value"]), value
            return
        for key, child in value.items():
            yield from _leaves(child, f"{trail}.{key}".strip("."))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _leaves(child, f"{trail}[{index}]")
    elif isinstance(value, (str, int, float, bool)) and str(value).strip():
        yield trail, str(value), {}


def _fingerprint(text: str) -> str:
    # File-backed scalar leaves may be prefixed by their JSON path.  The value
    # remains the same memory and should deduplicate against a structured fact.
    if ": " in text:
        text = text.rsplit(": ", 1)[-1]
    normalized = " ".join(
        "".join(char.lower() if char.isalnum() else " " for char in text).split()
    )
    return hashlib.sha1(normalized.encode()).hexdigest()


def _recency(value: Any, now: datetime) -> float:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return 1 / (1 + max(0.0, (now - parsed).total_seconds() / 86400) / 30)
    except (TypeError, ValueError):
        return 0.35
