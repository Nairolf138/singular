import logging

import pytest

from singular.events.bus import EventBus, Event, get_bus_strict_from_env


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
