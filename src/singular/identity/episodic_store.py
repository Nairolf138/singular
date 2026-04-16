"""Raw timestamped episodic journal with retention-aware compaction."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable

from ..io_utils import append_jsonl_line, atomic_write_text


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class EpisodicStore:
    """Persistent append-only JSONL store for short-term episodes."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def append(self, episode: dict[str, Any]) -> dict[str, Any]:
        payload = dict(episode)
        payload.setdefault("ts", _now_iso())
        append_jsonl_line(self.path, payload, with_lock=True)
        return payload

    def read_all(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    rows.append(parsed)
        return rows

    def truncate_to_rows(self, rows: Iterable[dict[str, Any]]) -> None:
        serialized = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        atomic_write_text(self.path, serialized)

    def compact(
        self,
        *,
        keep_last: int,
        preserve_identity_events: bool = True,
    ) -> dict[str, Any]:
        """Retain recent events while preserving identity invariants."""

        events = self.read_all()
        if keep_last < 0:
            keep_last = 0
        if len(events) <= keep_last:
            return {"compacted": False, "total": len(events), "kept": len(events)}

        retained = events[-keep_last:] if keep_last else []
        if preserve_identity_events:
            retained_ids = {id(row) for row in retained}
            invariants = [
                row
                for row in events
                if row.get("event") in {"identity.created", "identity.invariant"}
                and id(row) not in retained_ids
            ]
            retained = invariants + retained

        self.truncate_to_rows(retained)
        return {
            "compacted": True,
            "total": len(events),
            "kept": len(retained),
            "dropped": len(events) - len(retained),
        }
