"""Hashed JSONL logging for kernel events."""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict


class JsonlLogger:
    """Append-only JSONL logger with hash chaining."""

    def __init__(self, path: str = "kernel.log") -> None:
        self.path = path
        self.prev_hash = "0" * 64
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf8") as fh:
                    for line in fh:
                        pass
                if line:
                    data = json.loads(line)
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
        with open(self.path, "a", encoding="utf8") as fh:
            fh.write(json.dumps(entry) + "\n")
        self.prev_hash = current_hash


__all__ = ["JsonlLogger"]
