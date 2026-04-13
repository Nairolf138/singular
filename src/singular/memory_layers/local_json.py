from __future__ import annotations

from collections import Counter
from pathlib import Path
import json
import math
import re

from .base import MemoryBackend, MemoryRecord

_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


class LocalJsonMemoryBackend(MemoryBackend):
    """Simple local backend based on JSONL files and lexical similarity."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
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
                payload = json.loads(line)
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
        with path.open("w", encoding="utf-8") as handle:
            for rec in records:
                handle.write(
                    json.dumps(
                        {"id": rec.id, "text": rec.text, "metadata": rec.metadata}
                    )
                    + "\n"
                )

    def put(self, layer: str, record: MemoryRecord) -> None:
        records = [r for r in self._read_layer(layer) if r.id != record.id]
        records.append(record)
        self._write_layer(layer, records)

    def search(self, layer: str, query: str, limit: int = 5) -> list[MemoryRecord]:
        query_vec = _vectorize(query)
        scored: list[MemoryRecord] = []
        for rec in self._read_layer(layer):
            rec.score = _cosine(query_vec, _vectorize(rec.text))
            scored.append(rec)
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[: max(0, limit)]

    def delete(self, layer: str, record_id: str) -> bool:
        records = self._read_layer(layer)
        filtered = [rec for rec in records if rec.id != record_id]
        self._write_layer(layer, filtered)
        return len(filtered) != len(records)


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
