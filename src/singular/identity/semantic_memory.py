"""Semantic memory extraction and consolidation from episodic events."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from ..io_utils import atomic_write_text


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fact_key(fact: dict[str, Any]) -> str:
    canonical = json.dumps(fact, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:16]


class SemanticMemoryStore:
    """Consolidated facts extracted from episodic events."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            atomic_write_text(self.path, "[]")

    def read_facts(self) -> list[dict[str, Any]]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    def write_facts(self, facts: list[dict[str, Any]]) -> None:
        atomic_write_text(self.path, json.dumps(facts, ensure_ascii=False, indent=2) + "\n")

    def extract_facts(self, episodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        extracted: list[dict[str, Any]] = []
        for episode in episodes:
            ts = str(episode.get("ts") or _now_iso())
            for key in ("user_fact", "preference", "constraint"):
                value = episode.get(key)
                if isinstance(value, str) and value.strip():
                    extracted.append(
                        {
                            "id": _fact_key({"kind": key, "value": value.strip()}),
                            "kind": key,
                            "value": value.strip(),
                            "first_seen": ts,
                            "last_seen": ts,
                            "mentions": 1,
                            "confidence": 0.6,
                        }
                    )
        return extracted

    def merge_facts(self, new_facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        current = {fact.get("id"): fact for fact in self.read_facts() if fact.get("id")}
        for fact in new_facts:
            fid = fact.get("id")
            if fid in current:
                existing = current[fid]
                mentions = int(existing.get("mentions", 1)) + 1
                existing["mentions"] = mentions
                existing["last_seen"] = fact.get("last_seen") or fact.get("first_seen")
                existing["confidence"] = min(0.99, round(0.5 + mentions * 0.1, 2))
            else:
                current[fid] = fact
        merged = sorted(current.values(), key=lambda item: (str(item.get("kind")), str(item.get("value"))))
        self.write_facts(merged)
        return merged

    def consolidate_from_episodes(self, episodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self.merge_facts(self.extract_facts(episodes))
