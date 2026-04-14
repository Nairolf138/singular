import logging

import pytest

from singular.events.bus import (
    HELP_ACCEPTED,
    HELP_COMPLETED,
    HELP_OFFERED,
    HELP_REQUESTED,
    EventBus,
    Event,
    STANDARD_HELP_EVENTS,
    build_help_event_payload,
    get_bus_strict_from_env,
)


def test_dispatch_logs_handler_error(caplog: pytest.LogCaptureFixture) -> None:
    bus = EventBus(mode="sync")

    def failing_handler(event: Event) -> None:
        raise RuntimeError("boom")

    bus.subscribe("test.event", failing_handler)
    caplog.set_level(logging.ERROR, logger="singular.events.bus")

    bus.publish("test.event", {"ok": True})

    assert "Error while handling event 'test.event'" in caplog.text
    assert "failing_handler" in caplog.text


def test_dispatch_reraises_in_strict_mode() -> None:
    bus = EventBus(mode="sync", strict=True)

    def failing_handler(event: Event) -> None:
        raise ValueError("strict failure")

    bus.subscribe("test.event", failing_handler)

    with pytest.raises(ValueError, match="strict failure"):
        bus.publish("test.event", {"ok": True})


def test_get_bus_strict_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SINGULAR_EVENT_BUS_STRICT", "true")
    assert get_bus_strict_from_env() is True

    monkeypatch.setenv("SINGULAR_EVENT_BUS_STRICT", "0")
    assert get_bus_strict_from_env() is False


def test_standard_help_events_and_payload_builder() -> None:
    assert STANDARD_HELP_EVENTS == {
        HELP_REQUESTED,
        HELP_OFFERED,
        HELP_ACCEPTED,
        HELP_COMPLETED,
    }
    payload = build_help_event_payload(
        requester_life="life-a",
        helper_life="life-b",
        task="routine.fix_bug",
        attempts=4,
        metadata={"reason": "streak"},
    )
    assert payload["requester_life"] == "life-a"
    assert payload["helper_life"] == "life-b"
    assert payload["task"] == "routine.fix_bug"
    assert payload["attempts"] == 4
