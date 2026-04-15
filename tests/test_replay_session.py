from __future__ import annotations

from pathlib import Path
import json

from tools.replay_session import main


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row) + "\n")


def test_replay_session_returns_zero_when_lineage_is_consistent(tmp_path: Path, capsys) -> None:
    log_path = tmp_path / "audit.jsonl"
    _write_jsonl(
        log_path,
        [
            {
                "ts": "2026-04-15T10:00:00Z",
                "session_id": "s1",
                "category": "decision",
                "event_id": "evt-1",
                "intent_id": "intent-1",
                "action_id": None,
                "data": {"choice": "proceed"},
            },
            {
                "ts": "2026-04-15T10:00:01Z",
                "session_id": "s1",
                "category": "action",
                "event_id": "evt-1",
                "intent_id": "intent-1",
                "action_id": "act-1",
                "data": {"tool": "shell"},
            },
            {
                "ts": "2026-04-15T10:00:02Z",
                "session_id": "s1",
                "category": "result",
                "event_id": "evt-1",
                "intent_id": "intent-1",
                "action_id": "act-1",
                "data": {"ok": True},
            },
        ],
    )

    code = main([str(log_path), "--session-id", "s1"])
    output = capsys.readouterr().out

    assert code == 0
    assert "No lineage/correlation issue detected." in output


def test_replay_session_detects_missing_result(tmp_path: Path) -> None:
    log_path = tmp_path / "audit.jsonl"
    _write_jsonl(
        log_path,
        [
            {
                "ts": "2026-04-15T10:00:00Z",
                "session_id": "s1",
                "category": "decision",
                "event_id": "evt-1",
                "intent_id": "intent-1",
                "action_id": None,
                "data": {"choice": "proceed"},
            },
            {
                "ts": "2026-04-15T10:00:01Z",
                "session_id": "s1",
                "category": "action",
                "event_id": "evt-1",
                "intent_id": "intent-1",
                "action_id": "act-1",
                "data": {"tool": "shell"},
            },
        ],
    )

    code = main([str(log_path), "--session-id", "s1"])
    assert code == 3

