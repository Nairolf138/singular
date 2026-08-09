from __future__ import annotations

import json
import math
import os
import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import Callable

from .base import MemoryBackend, MemoryRecord

_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


class LocalJsonMemoryBackend(MemoryBackend):
    """Simple local backend based on JSONL files and lexical similarity."""

    def __init__(
        self, root: Path, *, embed: Callable[[str], list[float]] | None = None
    ) -> None:
        self.root = Path(root)
        self.embed = embed
        self.root.mkdir(parents=True, exist_ok=True)

    def _layer_path(self, layer: str) -> Path:
        return self.root / f"{layer}.jsonl"

    def _read_layer(self, layer: str) -> list[MemoryRecord]:
        path = self._layer_path(layer)
        if not path.exists():
            return []
        records: list[MemoryRecord] = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                records.append(
                    MemoryRecord(
                        id=str(payload.get("id", "")),
                        text=str(payload.get("text", "")),
                        metadata=dict(payload.get("metadata", {})),
                    )
                )
        return records

    def _write_layer(self, layer: str, records: list[MemoryRecord]) -> None:
        path = self._layer_path(layer)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                for rec in records:
                    handle.write(
                        json.dumps(
                            {"id": rec.id, "text": rec.text, "metadata": rec.metadata},
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    def put(self, layer: str, record: MemoryRecord) -> None:
        records = [r for r in self._read_layer(layer) if r.id != record.id]
        records.append(record)
        self._write_layer(layer, records)

    def search(self, layer: str, query: str, limit: int = 5) -> list[MemoryRecord]:
        scored: list[MemoryRecord] = []
        for rec in self._read_layer(layer):
            rec.score = self.similarity(query, rec.text)
            scored.append(rec)
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[: max(0, limit)]

    def delete(self, layer: str, record_id: str) -> bool:
        records = self._read_layer(layer)
        filtered = [rec for rec in records if rec.id != record_id]
        self._write_layer(layer, filtered)
        return len(filtered) != len(records)

    def similarity(self, query: str, text: str) -> float:
        """Use configured embeddings, falling back safely to local token vectors."""
        if self.embed is not None:
            try:
                return _dense_cosine(self.embed(query), self.embed(text))
            except (OSError, RuntimeError, TypeError, ValueError):
                pass
        return _cosine(_vectorize(query), _vectorize(text))


def _vectorize(text: str) -> Counter[str]:
    return Counter(token.lower() for token in _TOKEN_RE.findall(text))


def _cosine(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[k] * b[k] for k in a.keys() & b.keys())
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _dense_cosine(a: list[float], b: list[float]) -> float:
    if not a or len(a) != len(b):
        return 0.0
    norm_a = math.sqrt(sum(value * value for value in a))
    norm_b = math.sqrt(sum(value * value for value in b))
    if not norm_a or not norm_b:
        return 0.0
    return sum(left * right for left, right in zip(a, b)) / (norm_a * norm_b)
