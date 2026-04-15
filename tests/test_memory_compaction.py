from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from singular.memory_compaction import compact_episodic_jsonl, compact_generations_jsonl


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_compact_episodic_keeps_recent_and_writes_snapshot_refs(tmp_path: Path) -> None:
    mem_dir = tmp_path / "mem"
    mem_dir.mkdir(parents=True, exist_ok=True)
    episodic = mem_dir / "episodic.jsonl"

    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [
        {"ts": (base + timedelta(minutes=i)).isoformat(), "event": "tick", "text": f"evt-{i}"}
        for i in range(8)
    ]
    episodic.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    result = compact_episodic_jsonl(
        mem_dir=mem_dir,
        keep_last_events=3,
        snapshot_chunk_size=2,
        max_examples_per_snapshot=2,
        now=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )

    assert result["compacted"] is True
    assert result["historical_events"] == 5
    assert result["kept_recent"] == 3
    assert result["snapshot_count"] == 3

    compacted = _read_jsonl(episodic)
    refs = [row for row in compacted if row.get("event") == "episodic.compaction.reference"]
    assert len(refs) == 3
    assert compacted[-3:] == rows[-3:]

    snapshot_file = tmp_path / refs[0]["snapshot"]
    payload = json.loads(snapshot_file.read_text(encoding="utf-8"))
    assert payload["kind"] == "episodic_compaction_snapshot"
    assert payload["range"]["event_count"] == 2


def test_compact_generations_keeps_recent_and_minimal_audit(tmp_path: Path) -> None:
    mem_dir = tmp_path / "mem"
    mem_dir.mkdir(parents=True, exist_ok=True)
    generations = mem_dir / "generations.jsonl"

    now = datetime(2026, 4, 15, tzinfo=timezone.utc)
    old_ts = (now - timedelta(days=90)).isoformat()
    recent_ts = (now - timedelta(days=5)).isoformat()

    rows = [
        {
            "generation_id": 1,
            "parent_generation_id": None,
            "run_id": "r1",
            "iteration": 1,
            "ts": old_ts,
            "skill": "alpha",
            "skill_path": "skills/alpha.py",
            "mutation": {"operator": "noop", "diff": "..."},
            "score": {"base": 1.0, "new": 1.0},
            "verdict": "accepted",
            "reason": "ok",
            "hash": {"parent": "p", "candidate": "c"},
            "snapshot": "runs/r1/gen.py",
            "stable": True,
            "security": {"policy": True},
        },
        {
            "generation_id": 2,
            "parent_generation_id": 1,
            "run_id": "r2",
            "iteration": 2,
            "ts": old_ts,
            "skill": "alpha",
            "skill_path": "skills/alpha.py",
            "mutation": {"operator": "mut1", "diff": "..."},
            "score": {"base": 1.0, "new": 2.0},
            "verdict": "rejected",
            "reason": "bad",
            "hash": {"parent": "p2", "candidate": "c2"},
            "snapshot": "runs/r2/gen.py",
            "stable": False,
        },
        {
            "generation_id": 3,
            "parent_generation_id": 1,
            "run_id": "r3",
            "iteration": 3,
            "ts": recent_ts,
            "skill": "beta",
            "skill_path": "skills/beta.py",
            "mutation": {"operator": "mut2", "diff": "..."},
            "score": {"base": 2.0, "new": 1.2},
            "verdict": "accepted",
            "reason": "better",
            "hash": {"parent": "p3", "candidate": "c3"},
            "snapshot": "runs/r3/gen.py",
            "stable": True,
        },
    ]
    generations.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    result = compact_generations_jsonl(
        mem_dir=mem_dir,
        recent_days=30,
        max_old_rejected_samples=1,
        now=now,
    )

    assert result["compacted"] is True
    compacted = _read_jsonl(generations)

    assert any(row.get("generation_id") == 3 and row.get("verdict") == "accepted" for row in compacted)

    old_audit = [row for row in compacted if row.get("generation_id") == 1]
    assert old_audit
    assert old_audit[0]["event"] == "generations.audit.minimal"
    assert "mutation" not in old_audit[0]

    assert any(row.get("event") == "generations.rejected.aggregate" for row in compacted)
    assert any(row.get("event") == "generations.compaction.meta" for row in compacted)
