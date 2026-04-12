"""Hashed JSONL logging for kernel events."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict


class JsonlLogger:
    """Append-only JSONL logger with hash chaining."""

    def __init__(self, path: str | Path = "kernel.log") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.prev_hash = "0" * 64
        if self.path.exists():
            try:
                with self.path.open("r", encoding="utf8") as fh:
                    last_line = None
                    for line in fh:
                        last_line = line
                if last_line:
                    data = json.loads(last_line)
                    self.prev_hash = data.get("hash", self.prev_hash)
            except Exception:
                # Corrupt log; continue chain from zero hash
                self.prev_hash = "0" * 64

    def log(self, record: Dict[str, Any]) -> None:
        payload = json.dumps(record, sort_keys=True)
        current_hash = hashlib.sha256((payload + self.prev_hash).encode()).hexdigest()
        entry = {
            **record,
            "prev": self.prev_hash,
            "hash": current_hash,
        }
        with self.path.open("a", encoding="utf8") as fh:
            fh.write(json.dumps(entry) + "\n")
        self.prev_hash = current_hash


__all__ = ["JsonlLogger"]
