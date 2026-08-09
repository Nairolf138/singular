"""Transactional synchronization of the mutable psyche and its narrative."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from singular.events import EventBus
from singular.io_utils import append_jsonl_line, atomic_write_text, file_lock
from singular.psyche import Mood, Psyche
from singular.self_narrative import TraitTrend, load, save, timeline_path

_TRAITS = ("curiosity", "patience", "playfulness", "optimism", "resilience")


@dataclass(frozen=True)
class SynchronizationResult:
    event_id: str
    psyche_version: int
    narrative_version: int
    source: str
    deltas: dict[str, float]
    recovered: bool = False


class IdentitySynchronizationService:
    """Apply and durably project identity events through a recoverable journal.

    The journal is the commit intent.  It is removed only after both JSON
    projections and the timeline record exist, so startup can finish a partial
    transaction.  Publication happens strictly after that commit point.
    """

    def __init__(
        self, life_home: Path | str = ".", *, bus: EventBus | None = None
    ) -> None:
        self.home = Path(life_home)
        self.mem = self.home / "mem"
        self.psyche_path = self.mem / "psyche.json"
        self.narrative_path = self.mem / "self_narrative.json"
        self.journal_path = self.mem / "identity_sync.pending.json"
        self.lock_path = self.mem / "identity_sync"
        self.bus = bus
        self.mem.mkdir(parents=True, exist_ok=True)
        self.recover()

    @staticmethod
    def _payload(psyche: Psyche) -> dict[str, Any]:
        # Psyche owns its serialization rules; writing to an in-memory-shaped
        # temporary sibling also keeps future fields centralized there.
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "psyche.json"
            psyche.save_state(path)
            return json.loads(path.read_text(encoding="utf-8"))

    def apply_event(
        self,
        event: Mapping[str, Any],
        *,
        psyche: Psyche | None = None,
        publish: bool = True,
    ) -> SynchronizationResult:
        with file_lock(self.lock_path):
            self._recover_locked()
            current = psyche or Psyche.load_state(self.psyche_path)
            event_id = str(event.get("event_id") or uuid4())
            source = str(event.get("source") or "unknown")
            if current.last_identity_event_id == event_id:
                narrative = load(self.narrative_path)
                return SynchronizationResult(
                    event_id,
                    current.psyche_version,
                    narrative.narrative_version,
                    source,
                    {},
                )

            before = {key: float(getattr(current, key)) for key in _TRAITS}
            requested = event.get("deltas", {})
            if isinstance(requested, Mapping):
                for key in _TRAITS:
                    if key in requested:
                        setattr(
                            current,
                            key,
                            max(0.0, min(1.0, before[key] + float(requested[key]))),
                        )
            mood = event.get("mood")
            if mood:
                current.feel(mood if isinstance(mood, Mood) else Mood(str(mood)))
            deltas = {
                key: round(float(getattr(current, key)) - before[key], 12)
                for key in _TRAITS
                if float(getattr(current, key)) != before[key]
            }
            current.psyche_version += 1
            current.last_identity_event_id = event_id

            narrative = load(self.narrative_path)
            narrative.narrative_version += 1
            narrative.psyche_version = current.psyche_version
            narrative.last_event_id = event_id
            narrative.last_source = source
            narrative.last_deltas = deltas
            for key in _TRAITS:
                value = float(getattr(current, key))
                previous = narrative.trait_trends.get(key, TraitTrend()).value
                narrative.trait_trends[key] = TraitTrend(
                    value=value,
                    trend="up"
                    if value > previous
                    else "down"
                    if value < previous
                    else "stable",
                )
            if isinstance(event.get("current_heading"), str):
                narrative.current_heading = str(event["current_heading"])

            stamp = datetime.now(timezone.utc).isoformat()
            psyche_payload = self._payload(current)
            narrative_payload = narrative.to_dict()
            record = {
                "recorded_at": stamp,
                "schema_version": narrative.schema_version,
                "record_type": "identity_sync",
                "event_id": event_id,
                "source": source,
                "psyche_version": current.psyche_version,
                "narrative_version": narrative.narrative_version,
                "deltas": deltas,
                "narrative": narrative_payload,
            }
            intent = {
                "psyche": psyche_payload,
                "narrative": narrative_payload,
                "timeline": record,
            }
            atomic_write_text(
                self.journal_path, json.dumps(intent, ensure_ascii=False, indent=2)
            )
            self._commit_intent(intent)
            self.journal_path.unlink(missing_ok=True)
            result = SynchronizationResult(
                event_id,
                current.psyche_version,
                narrative.narrative_version,
                source,
                deltas,
            )
        if publish and self.bus is not None:
            self.bus.publish(
                "self_narrative.updated",
                {"event_type": "self_narrative.updated", **result.__dict__},
                payload_version=2,
            )
        return result

    def _commit_intent(self, intent: Mapping[str, Any]) -> None:
        atomic_write_text(
            self.psyche_path, json.dumps(intent["psyche"], ensure_ascii=False, indent=2)
        )
        atomic_write_text(
            self.narrative_path,
            json.dumps(intent["narrative"], ensure_ascii=False, indent=2),
        )
        event_id = str(intent["timeline"]["event_id"])
        existing = (
            timeline_path(self.narrative_path).read_text(encoding="utf-8")
            if timeline_path(self.narrative_path).exists()
            else ""
        )
        recorded_ids: set[str] = set()
        for line in existing.splitlines():
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, Mapping) and parsed.get("event_id"):
                recorded_ids.add(str(parsed["event_id"]))
        if event_id not in recorded_ids:
            append_jsonl_line(
                timeline_path(self.narrative_path), dict(intent["timeline"])
            )

    def recover(self) -> SynchronizationResult | None:
        with file_lock(self.lock_path):
            return self._recover_locked()

    def _recover_locked(self) -> SynchronizationResult | None:
        if self.journal_path.exists():
            intent = json.loads(self.journal_path.read_text(encoding="utf-8"))
            self._commit_intent(intent)
            self.journal_path.unlink(missing_ok=True)
            item = intent["timeline"]
            return SynchronizationResult(
                str(item["event_id"]),
                int(item["psyche_version"]),
                int(item["narrative_version"]),
                str(item["source"]),
                dict(item.get("deltas", {})),
                True,
            )
        self.verify_and_repair()
        return None

    def verify_and_repair(self) -> bool:
        """Repair an old/divergent narrative from the authoritative psyche."""
        psyche = Psyche.load_state(self.psyche_path)
        narrative = load(self.narrative_path)
        if narrative.psyche_version == psyche.psyche_version:
            return False
        narrative.psyche_version = psyche.psyche_version
        narrative.narrative_version = max(
            narrative.narrative_version, psyche.psyche_version
        )
        narrative.last_event_id = psyche.last_identity_event_id
        for key in _TRAITS:
            narrative.trait_trends[key] = TraitTrend(
                value=float(getattr(psyche, key)), trend="stable"
            )
        save(narrative, self.narrative_path, record_snapshot=False)
        return True


# Concise alias for call sites and integrations.
IdentitySyncService = IdentitySynchronizationService
