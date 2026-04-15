"""Compaction routines for long-lived memory JSONL stores."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from random import Random
from typing import Any

from .io_utils import atomic_write_text, file_lock


UTC = timezone.utc


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _parse_ts(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def _write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    serialized = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    atomic_write_text(path, serialized)


def _extract_text(event: dict[str, Any]) -> str:
    for key in ("text", "summary", "message", "event", "event_type"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "(sans résumé)"


def compact_episodic_jsonl(
    *,
    mem_dir: Path | str,
    keep_last_events: int = 500,
    snapshot_chunk_size: int = 1000,
    max_examples_per_snapshot: int = 5,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compact ``mem/episodic.jsonl`` into summary snapshots + truncated JSONL."""

    root = Path(mem_dir)
    episodic_path = root / "episodic.jsonl"
    snapshots_dir = root / "episodic_snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    with file_lock(episodic_path):
        events = _read_jsonl(episodic_path)
        if len(events) <= max(keep_last_events, 0):
            return {
                "compacted": False,
                "reason": "below_threshold",
                "total_events": len(events),
                "kept_recent": len(events),
                "snapshots": [],
            }

        keep = max(0, keep_last_events)
        recent_events = events[-keep:] if keep else []
        historical = events[:-keep] if keep else events

        generated_at = (now or _now_utc()).isoformat()
        snapshot_refs: list[dict[str, Any]] = []
        chunk_size = max(1, snapshot_chunk_size)
        for offset in range(0, len(historical), chunk_size):
            chunk = historical[offset : offset + chunk_size]
            ts_values = [dt for entry in chunk if (dt := _parse_ts(entry.get("ts"))) is not None]
            event_kinds: dict[str, int] = defaultdict(int)
            for entry in chunk:
                kind = entry.get("event") or entry.get("event_type") or "unknown"
                event_kinds[str(kind)] += 1

            examples = [_extract_text(item) for item in chunk[: max(1, max_examples_per_snapshot)]]
            canonical = "\n".join(
                json.dumps(item, ensure_ascii=False, sort_keys=True)
                for item in chunk
            )
            digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            snapshot_payload = {
                "schema_version": 1,
                "kind": "episodic_compaction_snapshot",
                "generated_at": generated_at,
                "source": "mem/episodic.jsonl",
                "range": {
                    "start_index": offset,
                    "end_index": offset + len(chunk) - 1,
                    "event_count": len(chunk),
                    "ts_min": min(ts_values).isoformat() if ts_values else None,
                    "ts_max": max(ts_values).isoformat() if ts_values else None,
                },
                "event_histogram": dict(sorted(event_kinds.items())),
                "examples": examples,
                "digest": digest,
            }
            snapshot_path = snapshots_dir / (
                f"episodic-{generated_at.replace(':', '').replace('+', '_')}"
                f"-{offset:08d}-{offset + len(chunk) - 1:08d}.json"
            )
            atomic_write_text(snapshot_path, json.dumps(snapshot_payload, ensure_ascii=False, indent=2))
            snapshot_refs.append(
                {
                    "snapshot": str(snapshot_path.relative_to(root.parent)),
                    "range": snapshot_payload["range"],
                    "digest": digest,
                }
            )

        compacted_rows = [
            {
                "event": "episodic.compaction.reference",
                "ts": generated_at,
                "snapshot": ref["snapshot"],
                "range": ref["range"],
                "digest": ref["digest"],
            }
            for ref in snapshot_refs
        ]
        compacted_rows.extend(recent_events)

        _write_jsonl_atomic(episodic_path, compacted_rows)

    return {
        "compacted": True,
        "total_events": len(events),
        "historical_events": len(historical),
        "kept_recent": len(recent_events),
        "snapshot_count": len(snapshot_refs),
        "snapshots": snapshot_refs,
    }


def _audit_projection(entry: dict[str, Any]) -> dict[str, Any]:
    """Keep only rollback/documentation-critical keys for old accepted entries."""

    hash_payload = entry.get("hash") if isinstance(entry.get("hash"), dict) else {}
    return {
        "event": "generations.audit.minimal",
        "ts": entry.get("ts"),
        "generation_id": entry.get("generation_id"),
        "parent_generation_id": entry.get("parent_generation_id"),
        "run_id": entry.get("run_id"),
        "iteration": entry.get("iteration"),
        "skill": entry.get("skill"),
        "skill_path": entry.get("skill_path"),
        "verdict": entry.get("verdict"),
        "stable": entry.get("stable"),
        "snapshot": entry.get("snapshot"),
        "reason": entry.get("reason"),
        "hash": {
            "parent": hash_payload.get("parent"),
            "candidate": hash_payload.get("candidate"),
        },
    }


def compact_generations_jsonl(
    *,
    mem_dir: Path | str,
    recent_days: int = 30,
    max_old_rejected_samples: int = 200,
    sampling_seed: int = 7,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compact ``mem/generations.jsonl`` while preserving rollback-grade auditability."""

    root = Path(mem_dir)
    generations_path = root / "generations.jsonl"

    with file_lock(generations_path):
        rows = _read_jsonl(generations_path)
        if not rows:
            return {
                "compacted": False,
                "reason": "empty",
                "total_rows": 0,
                "written_rows": 0,
            }

        ref_now = now or _now_utc()
        cutoff = ref_now - timedelta(days=max(1, recent_days))

        recent_rows: list[dict[str, Any]] = []
        old_accepted: list[dict[str, Any]] = []
        old_rejected: list[dict[str, Any]] = []
        for row in rows:
            ts = _parse_ts(row.get("ts"))
            verdict = str(row.get("verdict", "")).lower()
            is_recent = ts is None or ts >= cutoff
            if is_recent:
                recent_rows.append(row)
                continue
            if verdict == "accepted":
                old_accepted.append(row)
            else:
                old_rejected.append(row)

        sampled_rejected = sorted(
            Random(sampling_seed).sample(
                old_rejected,
                k=min(len(old_rejected), max(0, max_old_rejected_samples)),
            ),
            key=lambda item: int(item.get("generation_id", 0) or 0),
        )

        rejected_aggregate: dict[tuple[str, str], dict[str, Any]] = {}
        for row in old_rejected:
            skill = str(row.get("skill", "unknown"))
            mutation = row.get("mutation") if isinstance(row.get("mutation"), dict) else {}
            operator = str(mutation.get("operator", "unknown"))
            key = (skill, operator)
            slot = rejected_aggregate.setdefault(
                key,
                {
                    "event": "generations.rejected.aggregate",
                    "skill": skill,
                    "operator": operator,
                    "count": 0,
                    "score_delta_sum": 0.0,
                },
            )
            score = row.get("score") if isinstance(row.get("score"), dict) else {}
            try:
                base = float(score.get("base", 0.0) or 0.0)
                new = float(score.get("new", 0.0) or 0.0)
            except (TypeError, ValueError):
                base = 0.0
                new = 0.0
            slot["count"] += 1
            slot["score_delta_sum"] += (new - base)

        compacted_rows: list[dict[str, Any]] = []
        compacted_rows.extend(recent_rows)
        compacted_rows.extend(_audit_projection(item) for item in old_accepted)
        compacted_rows.extend(_audit_projection(item) for item in sampled_rejected)
        compacted_rows.extend(
            {**value, "score_delta_avg": (value["score_delta_sum"] / value["count"]) if value["count"] else 0.0}
            for value in sorted(rejected_aggregate.values(), key=lambda v: (str(v["skill"]), str(v["operator"])))
        )
        compacted_rows.append(
            {
                "event": "generations.compaction.meta",
                "ts": ref_now.isoformat(),
                "policy": {
                    "recent_days": max(1, recent_days),
                    "max_old_rejected_samples": max(0, max_old_rejected_samples),
                },
                "stats": {
                    "total_rows_before": len(rows),
                    "recent_rows_kept": len(recent_rows),
                    "old_accepted_audited": len(old_accepted),
                    "old_rejected_total": len(old_rejected),
                    "old_rejected_sampled": len(sampled_rejected),
                    "old_rejected_aggregate_groups": len(rejected_aggregate),
                },
            }
        )

        _write_jsonl_atomic(generations_path, compacted_rows)

    return {
        "compacted": True,
        "total_rows_before": len(rows),
        "total_rows_after": len(compacted_rows),
        "recent_rows_kept": len(recent_rows),
        "old_accepted_audited": len(old_accepted),
        "old_rejected_sampled": len(sampled_rejected),
        "old_rejected_aggregate_groups": len(rejected_aggregate),
    }


__all__ = [
    "compact_episodic_jsonl",
    "compact_generations_jsonl",
]
