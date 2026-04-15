from __future__ import annotations

from pathlib import Path

from observability.audit_log import AuditLogStore, read_audit_events


def test_audit_log_persists_correlated_records_and_redacts_sensitive_data(tmp_path: Path) -> None:
    store = AuditLogStore(root=tmp_path)

    decision = store.log_decision(
        session_id="session-1",
        event_id="evt-1",
        intent_id="intent-1",
        decision={"policy": "allow", "api_key": "super-secret-key"},
    )
    assert decision["event_id"] == "evt-1"
    assert decision["intent_id"] == "intent-1"
    assert decision["data"]["api_key"].startswith("<redacted:")

    action = store.log_action(
        session_id="session-1",
        event_id="evt-1",
        intent_id="intent-1",
        action={"tool": "shell", "prompt": "Contact me at ops@example.com"},
        action_id="act-1",
    )
    assert action["action_id"] == "act-1"
    assert action["data"]["prompt"] == "Contact me at <redacted:email>"

    store.log_result(
        session_id="session-1",
        event_id="evt-1",
        intent_id="intent-1",
        action_id="act-1",
        result={"ok": True, "token": "abcdefghijklmnopqrstuvwxyz123456"},
    )

    events = read_audit_events(tmp_path / "mem" / "audit_events.jsonl")
    assert len(events) == 3
    assert {event["category"] for event in events} == {"decision", "action", "result"}
    assert all(event["event_id"] == "evt-1" for event in events)

